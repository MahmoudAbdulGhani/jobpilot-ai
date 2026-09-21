import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import httpx
import pytest
from fastapi import HTTPException
from openai import OpenAI
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import (AIUsage, CandidateProfile, InterviewSession, InterviewOperation, Resume, ResumeExtraction, User)
from app.schemas.interviews import Advance, AnswerSave, InterviewSelection, InterviewStart, InterviewOutput
from app.services import interview_service as service
from app.services.ai_provider import ProviderFailure
from app.services.application_pack_service import PackError
from app.services.interview_provider import (TestInterviewProvider as Synthetic, OpenAIInterviewProvider, InterviewResult, request_bytes)
from consent_helpers import grant_consent
from test_email_applications import seed, settings as mailbox_settings


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda *a, **kw: pytest.fail('No live AI or Google calls'))


@pytest.fixture()
def settings(mailbox_settings):
    return mailbox_settings.model_copy(update={'JOBPILOT_AI_ENABLED':True,'JOBPILOT_AI_TEST_PROVIDER':True,
        'E2E_TEST_MODE':True,'POSTGRES_DB':mailbox_settings.POSTGRES_TEST_DB,
        'JOBPILOT_AI_MAX_REQUESTS_PER_USER':20})


def sources(db, settings):
    data=seed(db,settings)
    data.job.description='Build Python APIs and explain database trade-offs.'
    data.resume=db.scalar(select(Resume).where(Resume.owner_id==data.owner.id))
    data.extraction=db.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id==data.resume.id))
    data.profile=db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id==data.owner.id))
    data.profile.headline='Synthetic backend engineer'
    db.commit()
    return data


@pytest.fixture()
def data(db_session,settings):
    return sources(db_session,settings)


def begin(db,data,settings,**changes):
    selection=InterviewSelection(resume_id=data.resume.id,mode='mixed',question_count=2,**changes)
    prepared=service.preview(db,data.owner.id,data.job.id,selection,settings)
    body=InterviewStart(**selection.model_dump(),request_key=uuid.uuid4(),preview_hash=prepared['preview_hash'],confirm=True)
    return service.start(db,data.owner.id,data.job.id,body,settings),body


def advance(db,data,row,settings):
    grant_consent(db,data.owner.id,'ai_interview')
    body=Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True)
    return service.advance(db,data.owner.id,row.id,body,settings),body


def answer(db,data,row,text='I designed an API and checked its failure paths.'):
    return service.save_answer(db,data.owner.id,row.id,AnswerSave(revision=row.revision,question_number=len(row.turns),answer=text))


def test_snapshots_start_dedup_and_source_deletion(db_session,data,settings):
    row,body=begin(db_session,data,settings);snapshot=copy.deepcopy(row.source_snapshot)
    data.job.description='Changed job';data.extraction.draft_text='Changed CV';data.profile.headline='Changed profile';db_session.commit()
    assert service.start(db_session,data.owner.id,data.job.id,body,settings).id==row.id
    assert row.source_snapshot==snapshot
    db_session.delete(data.resume);db_session.commit()
    assert service.owned(db_session,data.owner.id,row.id).source_snapshot==snapshot
    assert db_session.get(AIUsage,data.owner.id) is None  # Preview/start sends no request.


def test_preview_rejects_changes_and_cross_owner_sources(db_session,data,settings):
    selection=InterviewSelection(resume_id=data.resume.id,mode='behavioral',question_count=2)
    preview=service.preview(db_session,data.owner.id,data.job.id,selection,settings)
    data.extraction.draft_text='Source changed';db_session.commit()
    with pytest.raises(PackError,match='Sources or settings changed'):
        service.start(db_session,data.owner.id,data.job.id,InterviewStart(**selection.model_dump(),request_key=uuid.uuid4(),preview_hash=preview['preview_hash'],confirm=True),settings)
    from app.models import SavedJob
    other_job=SavedJob(owner_id=data.other.id,title='Other job',company='Other',description='Other requirement')
    db_session.add(other_job);db_session.commit()
    with pytest.raises(PackError,match='CV not found'):
        service.capture(db_session,data.other.id,other_job.id,selection)
    with pytest.raises(PackError):service.capture(db_session,data.other.id,data.job.id,selection)
    data.extraction.reviewed_at=None;db_session.commit()
    with pytest.raises(PackError,match='Confirm nonempty'):service.capture(db_session,data.owner.id,data.job.id,selection)


def test_approved_pack_version_snapshot(db_session,data,settings):
    selection=InterviewSelection(pack_id=data.pack.id,pack_version=1,mode='technical',question_count=2)
    preview=service.preview(db_session,data.owner.id,data.job.id,selection,settings)
    assert preview['source_snapshot']['cv_text']=='Supported CV'
    assert preview['source_snapshot']['cover_letter_text']=='Supported letter'
    data.version.approved_at=None;db_session.commit()
    with pytest.raises(PackError,match='approved'):service.capture(db_session,data.owner.id,data.job.id,selection)


def test_complete_resume_dedup_and_strict_feedback(db_session,data,settings):
    row,_=begin(db_session,data,settings)
    row,key=advance(db_session,data,row,settings)
    assert len(row.turns)==1 and row.turns[0]['category']=='behavioral'
    service.advance(db_session,data.owner.id,row.id,key,settings)
    assert db_session.get(AIUsage,data.owner.id).requests==1
    row=answer(db_session,data,row);saved=row.turns[-1]['answer']
    db_session.expire_all();row=service.owned(db_session,data.owner.id,row.id)
    assert row.turns[-1]['answer']==saved
    row,_=advance(db_session,data,row,settings)
    assert len(row.turns)==2 and row.turns[-1]['category']=='technical'
    assert row.turns[-1]['question']['quote'] in saved
    row=answer(db_session,data,row,'I would test latency and compare query plans; this is a hypothetical proposal.')
    row,_=advance(db_session,data,row,settings)
    result=service.public(db_session,row)
    assert row.status=='completed' and all(t['feedback'] for t in row.turns)
    assert result['practice_priorities'] and db_session.get(AIUsage,data.owner.id).requests==3
    with pytest.raises(PackError):advance(db_session,data,row,settings)
    service.delete(db_session,data.owner.id,row.id)
    assert db_session.scalar(select(func.count()).select_from(InterviewOperation).where(InterviewOperation.session_id==row.id))==0
    assert db_session.get(AIUsage,data.owner.id).requests==3  # Deletion never refunds quota.


def test_api_owner_isolation_and_resume(client,db_session,data,settings):
    client.app.dependency_overrides[get_db]=lambda:db_session
    client.app.dependency_overrides[get_settings]=lambda:settings
    row,_=begin(db_session,data,settings)
    grant_consent(db_session,data.other.id,'ai_interview')  # Other is consented: isolation must still hold.
    h=lambda user:{'Authorization':'Bearer '+create_access_token(user.id)}
    try:
        for method,path,body in [('get',f'/interviews/{row.id}',None),('delete',f'/interviews/{row.id}',None),
            ('post',f'/interviews/{row.id}/advance',dict(request_key=str(uuid.uuid4()),revision=0,confirm=True)),
            ('patch',f'/interviews/{row.id}/answer',dict(revision=0,question_number=1,answer='Other user'))]:
            kwargs={'headers':h(data.other)}
            if body is not None:kwargs['json']=body
            assert getattr(client,method)('/api'+path,**kwargs).status_code==404
        assert client.get(f'/api/jobs/{data.job.id}/interviews/options',headers=h(data.other)).status_code==404
        assert client.get(f'/api/interviews/{row.id}',headers=h(data.owner)).json()['source_snapshot']['cv_text']=='Synthetic CV'
        assert client.get(f'/api/jobs/{data.job.id}/interviews',headers=h(data.owner)).json()['items'][0]['id']==str(row.id)
    finally:
        client.app.dependency_overrides.pop(get_db,None);client.app.dependency_overrides.pop(get_settings,None)


@pytest.mark.parametrize('failure',['exception','timeout','bad_quote','invented_claim'])
def test_failure_retains_answer_no_retry(db_session,data,settings,monkeypatch,failure):
    row,_=begin(db_session,data,settings);row,_=advance(db_session,data,row,settings);row=answer(db_session,data,row)
    saved=copy.deepcopy(row.turns);calls=[]
    class Broken:
        def practice(self,payload):
            calls.append(payload)
            if failure=='exception':raise RuntimeError('SECRET body must not escape')
            raw=Synthetic().practice(payload).output.model_dump()
            if failure=='bad_quote':raw['feedback']['specificity']['answer_quotes']=['Fabricated experience at Imaginary Inc']
            else:raw['feedback']['candidate_claim']='You led 20 engineers'
            return InterviewResult(raw)
    monkeypatch.setattr(service,'provider_for',lambda *a:Broken())
    if failure=='timeout':
        monkeypatch.setattr(service.ai_usage,'bounded_call',lambda *a: (_ for _ in ()).throw(ProviderFailure('timeout')))
    row,key=advance(db_session,data,row,settings)
    assert row.status=='interrupted' and row.turns==saved
    assert 'SECRET' not in json.dumps(service.public(db_session,row),default=str)
    service.advance(db_session,data.owner.id,row.id,key,settings)
    assert len(calls)==(0 if failure=='timeout' else 1)
    assert db_session.get(AIUsage,data.owner.id).requests==2


def test_quotas_input_limits_and_guarded_provider(db_session,data,settings):
    row,_=begin(db_session,data,settings)
    limited=settings.model_copy(update={'JOBPILOT_AI_MAX_REQUESTS_PER_USER':0})
    with pytest.raises(PackError,match='request limit'):advance(db_session,data,row,limited)
    assert not row.turns
    db_session.rollback()
    with pytest.raises(PackError,match='restricted'):
        service.configuration(settings.model_copy(update={'E2E_TEST_MODE':False}))
    with pytest.raises(PackError,match='input limit'):
        advance(db_session,data,row,settings.model_copy(update={'JOBPILOT_INTERVIEW_MAX_INPUT_BYTES':1}))
    with pytest.raises(PackError,match='session limit'):
        begin(db_session,data,settings.model_copy(update={'JOBPILOT_INTERVIEW_MAX_SESSIONS_PER_USER':1}))


def test_expired_operation_and_stale_answer(client,db_session,data,settings):
    row,_=begin(db_session,data,settings);row,_=advance(db_session,data,row,settings);row=answer(db_session,data,row)
    op=InterviewOperation(id=uuid.uuid4(),session_id=row.id,request_key=uuid.uuid4(),request_hash='x',step=1,status='pending',deadline=service.now()-timedelta(seconds=1))
    db_session.add(op);row.active_operation=op.id;row.status='generating';db_session.commit()
    assert service.public(db_session,row)['status']=='interrupted'
    client.app.dependency_overrides[get_db]=lambda:db_session
    try:
        listing=client.get(f'/api/jobs/{data.job.id}/interviews',headers={'Authorization':'Bearer '+create_access_token(data.owner.id)})
        assert listing.json()['items'][0]['status']=='interrupted'
    finally:
        client.app.dependency_overrides.pop(get_db,None)
    row=answer(db_session,data,row,'Saved after interruption')
    assert row.status=='interrupted' and op.status=='failed'
    with pytest.raises(PackError,match='Session changed'):
        service.save_answer(db_session,data.owner.id,row.id,AnswerSave(revision=0,question_number=1,answer='stale'))
    row,_=advance(db_session,data,row,settings)
    assert len(row.turns)==2


def test_actual_sdk_wire_minimal_strict_required_and_incomplete():
    config={'model':'gpt-5-mini','reasoning':'minimal','max_output_tokens':2000,'timeout':60}
    payload={'source':{'job':{'description':'Build APIs'}},'latest_answer':None,'final':False,'next_category':'technical','allowed_strategies':['technical_approach'],'prior_questions':[]}
    requests=[]
    def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'resp_synthetic','object':'response','created_at':1,'model':'gpt-5-mini','status':'incomplete',
            'incomplete_details':{'reason':'max_output_tokens'},'output':[]})
    with OpenAI(api_key='offline-placeholder',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        with pytest.raises(ProviderFailure):OpenAIInterviewProvider('offline-placeholder',config,client).practice(payload)
    wire=requests[0]
    assert wire['reasoning']=={'effort':'minimal'} and wire['max_output_tokens']==2000 and wire['store'] is False
    assert wire['text']['format']['strict'] is True
    assert wire['text']['format']['schema']==InterviewOutput.model_json_schema()
    assert set(wire['text']['format']['schema']['required'])=={'question','feedback'}
    assert set(wire['text']['format']['schema']['$defs']['Criterion']['required'])=={'assessment','answer_quotes','focus'}
    assert len(json.dumps(wire,ensure_ascii=False).encode())<=request_bytes(payload,config)
    assert len(requests)==1 and 'tools' not in wire


def test_http_rejection_has_zero_sdk_retries():
    calls=[]
    config={'model':'gpt-5-mini','reasoning':'minimal','max_output_tokens':2000,'timeout':60}
    def transport(request):
        calls.append(1)
        return httpx.Response(503,json={'error':{'message':'Unrestricted provider body must not escape'}})
    with OpenAI(api_key='offline-placeholder',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        with pytest.raises(ProviderFailure,match='provider_or_validation_failure'):
            OpenAIInterviewProvider('offline-placeholder',config,client).practice({})
    assert len(calls)==1


def test_retry_allowance_is_explicit_and_bounded(db_session,data,settings,monkeypatch):
    row,_=begin(db_session,data,settings)
    class Broken:
        def practice(self,payload):raise ProviderFailure('incomplete_or_refused')
    monkeypatch.setattr(service,'provider_for',lambda *a:Broken())
    row,_=advance(db_session,data,row,settings)
    assert row.status=='interrupted'
    row,_=advance(db_session,data,row,settings)
    with pytest.raises(PackError,match='allowance exhausted'):advance(db_session,data,row,settings)
    assert db_session.get(AIUsage,data.owner.id).requests==2


@pytest.mark.parametrize('change',['empty_quotes','wrong_focus','stitched_quote','wrong_question_source','missing_required'])
def test_feedback_and_followup_fail_closed(db_session,data,settings,change):
    row,_=begin(db_session,data,settings);row,_=advance(db_session,data,row,settings);row=answer(db_session,data,row)
    payload=service.request_payload(row);raw=Synthetic().practice(payload).output.model_dump()
    if change=='empty_quotes':raw['feedback']['specificity']['answer_quotes']=[]
    elif change=='wrong_focus':raw['feedback']['specificity']['focus']='mechanism'
    elif change=='stitched_quote':raw['feedback']['specificity']['answer_quotes']=['I designed checked its failure paths.']
    elif change=='wrong_question_source':raw['question']['source']='job'
    else:del raw['feedback']['clarity']
    with pytest.raises(ValueError):service.validate_output(raw,payload)


def test_offline_plan_is_bounded_without_network():
    from app.evaluation.interview_plan import build_plan
    from decimal import Decimal
    plan=build_plan()
    assert plan['live_requests_sent']==0 and plan['planned_live_requests']==1
    assert Decimal(plan['estimated_budget_ceiling_usd'])>=Decimal(plan['calculated_estimate_usd'])


def test_interview_configuration_does_not_change_pack_or_profile_defaults(settings):
    before=(settings.JOBPILOT_AI_PROVIDER,settings.JOBPILOT_AI_MODEL,settings.JOBPILOT_PACK_MODEL,settings.JOBPILOT_PACK_MAX_OUTPUT_TOKENS)
    config,_=service.configuration(settings)
    assert config['max_output_tokens']==2000
    assert before==(settings.JOBPILOT_AI_PROVIDER,settings.JOBPILOT_AI_MODEL,settings.JOBPILOT_PACK_MODEL,settings.JOBPILOT_PACK_MAX_OUTPUT_TOKENS)


def test_concurrent_submissions_dispatch_once_and_delete_during_call(test_engine,settings,monkeypatch):
    entered,finish=Event(),Event();calls=[]
    class Slow(Synthetic):
        def practice(self,payload):
            calls.append(payload);entered.set();assert finish.wait(15);return super().practice(payload)
    monkeypatch.setattr(service,'provider_for',lambda *a:Slow())
    with Session(test_engine,expire_on_commit=False) as db:
        data=sources(db,settings);owner,other=data.owner.id,data.other.id
        grant_consent(db,owner,'ai_interview')
        row,_=begin(db,data,settings);id=row.id;body=Advance(request_key=uuid.uuid4(),revision=0,confirm=True)
    def dispatch():
        with Session(test_engine,expire_on_commit=False) as db:
            try:return service.advance(db,owner,id,body,settings).status
            except PackError as error:return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(dispatch);assert entered.wait(10)
            assert pool.submit(dispatch).result(timeout=10)=='generating'
            with Session(test_engine,expire_on_commit=False) as db:
                service.delete(db,owner,id)
            finish.set();assert future.result(timeout=10)==404
        assert len(calls)==1
        with Session(test_engine) as db:
            assert db.get(InterviewSession,id) is None and db.get(AIUsage,owner).requests==1
    finally:
        finish.set()
        with Session(test_engine) as db:
            db.execute(delete(User).where(User.id.in_([owner,other])));db.commit()


def test_advance_without_consent_never_calls_provider(db_session,data,settings,monkeypatch):
    row,_=begin(db_session,data,settings)
    def forbidden(db,*a):
        pytest.fail('Interview provider must not be called without consent')
    monkeypatch.setattr(service,'provider_for',forbidden)
    deny=Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True)
    with pytest.raises(HTTPException) as error:
        service.advance(db_session,data.owner.id,row.id,deny,settings)
    assert error.value.status_code==403
    assert 'consent' in str(error.value.detail).casefold()
    assert db_session.get(AIUsage,data.owner.id) is None
    assert db_session.scalar(select(func.count()).select_from(InterviewOperation).where(InterviewOperation.session_id==row.id))==0


def test_consent_is_owner_scoped(db_session,data,settings,monkeypatch):
    row,_=begin(db_session,data,settings)
    calls=[]
    class Recorder(Synthetic):
        def practice(self,payload):
            calls.append(payload);return super().practice(payload)
    monkeypatch.setattr(service,'provider_for',lambda *a:Recorder())
    grant_consent(db_session,data.other.id,'ai_interview')  # Only the other user is consented.
    with pytest.raises(HTTPException) as error:
        service.advance(db_session,data.owner.id,row.id,Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True),settings)
    assert error.value.status_code==403
    assert calls==[]  # The other user's consent must not enable the owner.
    with pytest.raises(PackError) as error:
        service.advance(db_session,data.other.id,row.id,Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True),settings)
    assert error.value.status_code==404  # Ownership still gates the consented foreign user.
    assert calls==[]


def test_revoked_consent_blocks_dispatch(db_session,data,settings,monkeypatch):
    row,_=begin(db_session,data,settings)
    calls=[]
    class Recorder(Synthetic):
        def practice(self,payload):
            calls.append(payload);return super().practice(payload)
    monkeypatch.setattr(service,'provider_for',lambda *a:Recorder())
    row,_=advance(db_session,data,row,settings)
    assert len(calls)==1 and db_session.get(AIUsage,data.owner.id).requests==1
    grant_consent(db_session,data.owner.id,'ai_interview',allowed=False)  # Revoked mid-session.
    with pytest.raises(HTTPException) as error:
        service.advance(db_session,data.owner.id,row.id,Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True),settings)
    assert error.value.status_code==403
    assert len(calls)==1  # No further provider call after revocation.


def test_consent_revoked_after_interview_reservation_finalizes_operation(db_session,data,settings,monkeypatch):
    from app.models import UsageReservation
    row,_=begin(db_session,data,settings)
    grant_consent(db_session,data.owner.id,'ai_interview')
    calls=[]
    class Recorder(Synthetic):
        def practice(self,payload):
            calls.append(payload);return super().practice(payload)
    monkeypatch.setattr(service,'provider_for',lambda *a:Recorder())
    original=service.ai_usage.reserve;reserved={}
    def revoke_after_reservation(*args,**kwargs):
        token=original(*args,**kwargs);reserved['token']=token
        grant_consent(db_session,data.owner.id,'ai_interview',allowed=False)
        return token
    monkeypatch.setattr(service.ai_usage,'reserve',revoke_after_reservation)
    body=Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True)
    with pytest.raises(HTTPException) as error:
        service.advance(db_session,data.owner.id,row.id,body,settings)
    assert error.value.status_code==403 and calls==[]
    db_session.refresh(row)
    operation=db_session.scalar(select(InterviewOperation).where(
        InterviewOperation.session_id==row.id,InterviewOperation.request_key==body.request_key))
    assert row.status=='interrupted' and row.active_operation is None
    assert operation.status=='failed' and operation.outcome=='consent_or_account_denied'
    usage=db_session.get(AIUsage,data.owner.id)
    assert usage.active_token is None and usage.active_until is None
    assert db_session.get(UsageReservation,reserved['token']).released_at is not None

    grant_consent(db_session,data.owner.id,'ai_interview')
    assert service.advance(db_session,data.owner.id,row.id,body,settings).id==row.id
    assert calls==[]  # Same request key returns the denied operation without redispatch.
    monkeypatch.setattr(service.ai_usage,'reserve',original)
    retry=Advance(request_key=uuid.uuid4(),revision=row.revision,confirm=True)
    completed=service.advance(db_session,data.owner.id,row.id,retry,settings)
    assert completed.status=='ready' and len(calls)==1
