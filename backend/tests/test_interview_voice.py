import copy
import io
import json
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import httpx
import pytest
from openai import OpenAI
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import AIUsage, InterviewSession, InterviewVoiceOperation, User
from app.services import interview_voice as voice, interview_service, account_data
from app.services.application_pack_service import PackError
from app.services.speech_provider import OpenAISpeechProvider, SyntheticSpeechProvider, SpeechFailure, SpeechResult, validate_recording
from consent_helpers import grant_consent
from test_email_applications import settings as mailbox_settings
from test_interviews import settings as interview_settings, sources, begin, advance, answer


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', lambda *a, **k: pytest.fail('Live network forbidden'))


@pytest.fixture
def settings(interview_settings):
    return interview_settings.model_copy(update={'JOBPILOT_VOICE_ENABLED':True,'JOBPILOT_VOICE_TEST_PROVIDER':True})


def wav(seconds=1):
    output=io.BytesIO()
    with wave.open(output,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*int(16000*seconds))
    return output.getvalue()


@pytest.fixture
def data(db_session,settings):
    data=sources(db_session,settings);data.session,_=begin(db_session,data,settings)
    data.session,_=advance(db_session,data,data.session,settings)
    data.session=answer(db_session,data,data.session,'Previously saved text answer.')
    # Voice consent for both users: ownership (not consent) must gate foreign access.
    grant_consent(db_session,data.owner.id,'ai_voice')
    grant_consent(db_session,data.other.id,'ai_voice')
    return data


def run(db,data,settings,key=None,kind='transcribe',audio=None,consent=True):
    return voice.run(db,data.owner.id,data.session.id,key or uuid.uuid4(),1,consent,kind,settings,wav() if audio is None else audio)


def test_draft_only_duplicate_quota_and_expiry(db_session,data,settings):
    before=copy.deepcopy(data.session.turns);revision=data.session.revision;key=uuid.uuid4()
    result=run(db_session,data,settings,key)
    assert result['status']=='succeeded' and result['transcript'].startswith('I built')
    assert run(db_session,data,settings,key)==result
    assert data.session.turns==before and data.session.revision==revision
    assert db_session.get(AIUsage,data.owner.id).requests==2
    assert result['usage']['actual_cost_usd'] is None
    assert result['usage']['estimated_cost_usd']=='0.000100'
    with pytest.raises(PackError,match='different content'):run(db_session,data,settings,key,audio=wav(2))
    row=db_session.get(InterviewVoiceOperation,uuid.UUID(result['id']))
    row.expires_at=voice.now()-timedelta(seconds=1);db_session.commit()
    assert run(db_session,data,settings,key)['transcript'] is None
    assert db_session.get(AIUsage,data.owner.id).requests==2


@pytest.mark.parametrize('change',['empty','html','truncated','trailing','wrong_rate','too_long','too_short'])
def test_audio_bytes_not_mime_or_name(change):
    audio=wav()
    if change=='empty':audio=b''
    elif change=='html':audio=b'<html>'+b'x'*32000
    elif change=='truncated':audio=audio[:-2]
    elif change=='trailing':audio+=b'x'
    elif change=='wrong_rate':audio=audio[:24]+(48000).to_bytes(4,'little')+audio[28:]
    elif change=='too_long':audio=wav(60.01)
    else:audio=wav(.1)
    with pytest.raises(SpeechFailure,match='invalid_audio'):validate_recording(audio,60)
    assert validate_recording(wav(.25),60)==.25
    assert validate_recording(wav(60),60)==60


def test_owner_consent_limits_and_guard(db_session,data,settings):
    with pytest.raises(PackError):voice.run(db_session,data.other.id,data.session.id,uuid.uuid4(),1,True,'transcribe',settings,wav())
    with pytest.raises(PackError,match='consent'):run(db_session,data,settings,consent=False)
    with pytest.raises(PackError,match='disabled'):run(db_session,data,settings.model_copy(update={'JOBPILOT_VOICE_ENABLED':False}))
    with pytest.raises(PackError,match='guarded'):voice.configuration(settings.model_copy(update={'E2E_TEST_MODE':False}))
    with pytest.raises(PackError,match='not configured'):voice.configuration(settings.model_copy(update={'JOBPILOT_VOICE_TEST_PROVIDER':False,'JOBPILOT_VOICE_API_KEY':''}))
    assert db_session.get(AIUsage,data.owner.id).requests==1
    run(db_session,data,settings)
    with pytest.raises(PackError,match='session'):run(db_session,data,settings.model_copy(update={'JOBPILOT_VOICE_MAX_CALLS_PER_SESSION':1}))
    with pytest.raises(PackError,match='account'):run(db_session,data,settings.model_copy(update={'JOBPILOT_AI_MAX_REQUESTS_PER_USER':2}))


@pytest.mark.parametrize('failure',['provider','empty','oversize','timeout'])
def test_provider_failure_retains_text_and_never_retries(db_session,data,settings,monkeypatch,failure):
    calls=[]
    class Broken:
        def transcribe(self,audio):
            calls.append(1)
            if failure=='provider':raise RuntimeError('PRIVATE provider explanation')
            return SpeechResult(transcript='' if failure=='empty' else 'x'*3001)
    monkeypatch.setattr(voice,'provider_for',lambda s:Broken())
    if failure=='timeout':monkeypatch.setattr(voice.ai_usage,'bounded_call',lambda *a:(_ for _ in ()).throw(TimeoutError('SECRET')))
    key=uuid.uuid4();result=run(db_session,data,settings,key)
    assert result['status']=='failed' and 'PRIVATE' not in json.dumps(result) and 'SECRET' not in json.dumps(result)
    assert run(db_session,data,settings,key)==result
    assert len(calls)==(0 if failure=='timeout' else 1)
    assert data.session.turns[-1]['answer']=='Previously saved text answer.'
    assert db_session.get(AIUsage,data.owner.id).requests==2


def test_speech_is_question_only_not_persisted(db_session,data,settings,monkeypatch):
    seen=[]
    class Provider(SyntheticSpeechProvider):
        def speak(self,text):seen.append(text);return super().speak(text)
    monkeypatch.setattr(voice,'provider_for',lambda s:Provider())
    key=uuid.uuid4();result=run(db_session,data,settings,key,kind='speak')
    turn=data.session.turns[0]
    assert result['audio'] and seen==[turn['text']+'\nRelevant excerpt: '+turn['question']['quote']]
    assert run(db_session,data,settings,key,kind='speak')['audio'] is None
    row=db_session.get(InterviewVoiceOperation,uuid.UUID(result['id']))
    assert row.transcript is None and result['audio'] not in str(row.__dict__)


def test_sdk_wire_and_failures_zero_retry(settings):
    requests=[]
    def transport(request):
        requests.append(request)
        if request.url.path.endswith('transcriptions'):
            assert b'whisper-1' in request.content and wav() in request.content
            return httpx.Response(200,json={'text':'Synthetic transcript'})
        body=json.loads(request.content)
        assert body=={'model':'tts-1','voice':'alloy','input':'A visible question?','response_format':'mp3'}
        return httpx.Response(200,content=b'ID3-synthetic-mp3',headers={'content-type':'audio/mpeg'})
    def client(handler):return OpenAI(api_key='offline-placeholder',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    first,second=client(transport),client(transport)
    assert OpenAISpeechProvider(settings,first).transcribe(wav()).transcript=='Synthetic transcript'
    assert OpenAISpeechProvider(settings,second).speak('A visible question?').audio==b'ID3-synthetic-mp3'
    assert first.is_closed() and second.is_closed()
    calls=[]
    def rejection(request):calls.append(1);return httpx.Response(503,json={'error':{'message':'PRIVATE'}})
    rejected=client(rejection)
    with pytest.raises(SpeechFailure,match='provider_unavailable'):
        OpenAISpeechProvider(settings,rejected).transcribe(wav())
    assert rejected.is_closed()
    assert len(calls)==1 and len(requests)==2


def test_api_raw_bounded_upload_and_ownership(client,db_session,data,settings):
    client.app.dependency_overrides[get_db]=lambda:db_session
    client.app.dependency_overrides[get_settings]=lambda:settings
    h=lambda user:{'Authorization':'Bearer '+create_access_token(user.id),'Content-Type':'audio/wav'}
    path=f'/api/interviews/{data.session.id}/voice/transcribe'
    query={'request_key':str(uuid.uuid4()),'question_number':1,'consent':'true'}
    try:
        assert client.post(path,params=query,headers=h(data.other),content=wav()).status_code==404
        assert client.post(path,params={**query,'consent':'false'},headers=h(data.owner),content=wav()).status_code==422
        assert client.post(path,params=query,headers=h(data.owner),content=b'x'*1_920_045).status_code==413
        invalid=client.post(path,params=query,headers=h(data.owner),content=b'PRIVATE not audio')
        assert invalid.status_code==422 and 'PRIVATE' not in invalid.text
        result=client.post(path,params=query,headers=h(data.owner),content=wav())
        assert result.status_code==200 and result.json()['status']=='succeeded'
        assert result.headers['cache-control']=='no-store'
        speech=f'/api/interviews/{data.session.id}/voice/speak'
        assert client.post(speech,headers={**h(data.other),'Content-Type':'application/json'},json={'request_key':str(uuid.uuid4()),'question_number':1,'consent':True}).status_code==404
    finally:client.app.dependency_overrides.clear()


def test_retained_transcript_export_deletion_and_cleanup(db_session,data,settings):
    result=run(db_session,data,settings)
    exported=list(db_session.execute(account_data.export_query('interview_voice_operations',data.owner.id)).mappings())
    assert exported[0]['transcript']==result['transcript'] and 'request_hash' not in exported[0]
    assert not list(db_session.execute(account_data.export_query('interview_voice_operations',data.other.id)))
    row=db_session.get(InterviewVoiceOperation,uuid.UUID(result['id']))
    # Restrict the retention exercise to this synthetic record. The production
    # command's broader rules are covered separately with preservation guards.
    row.expires_at=voice.now()-timedelta(seconds=1);db_session.commit()
    cutoff=voice.now()
    eligible=db_session.scalars(select(InterviewVoiceOperation.id).where(InterviewVoiceOperation.expires_at<=cutoff,InterviewVoiceOperation.transcript.is_not(None))).all()
    if set(eligible)!={row.id}:pytest.skip('Existing expiring transcripts preserved; retention mutation not exercised')
    assert account_data.voice_retention(db_session,cutoff)==1
    assert row.transcript is not None
    assert list(db_session.execute(account_data.export_query('interview_voice_operations',data.owner.id)).mappings())[0]['transcript'] is None
    assert account_data.voice_retention(db_session,cutoff,dry_run=False)==1
    db_session.commit()
    assert row.transcript is None and account_data.voice_retention(db_session,cutoff,dry_run=False)==0
    assert voice.public(row)['transcript'] is None
    identifier=row.id
    interview_service.delete(db_session,data.owner.id,data.session.id)
    assert db_session.get(InterviewVoiceOperation,identifier) is None
    assert db_session.get(AIUsage,data.owner.id).requests==2


def test_concurrent_once_and_deleted_session_no_late_write(test_engine,settings,monkeypatch):
    entered,finish=Event(),Event();calls=[]
    class Slow(SyntheticSpeechProvider):
        def transcribe(self,audio):calls.append(1);entered.set();assert finish.wait(15);return super().transcribe(audio)
    monkeypatch.setattr(voice,'provider_for',lambda s:Slow())
    with Session(test_engine,expire_on_commit=False) as db:
        data=sources(db,settings);owner,other=data.owner.id,data.other.id
        data.session,_=begin(db,data,settings);data.session,_=advance(db,data,data.session,settings)
        grant_consent(db,owner,'ai_voice')
        session_id=data.session.id;key=uuid.uuid4()
    def dispatch():
        with Session(test_engine,expire_on_commit=False) as db:
            try:return voice.run(db,owner,session_id,key,1,True,'transcribe',settings,wav())['status']
            except PackError as e:return e.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(dispatch);assert entered.wait(10)
            assert pool.submit(dispatch).result(timeout=10)=='pending'
            with Session(test_engine) as db:interview_service.delete(db,owner,session_id)
            finish.set();assert first.result(timeout=10)==404
        assert len(calls)==1
        with Session(test_engine) as db:
            assert db.get(InterviewSession,session_id) is None
            assert db.scalar(select(InterviewVoiceOperation.id).where(InterviewVoiceOperation.owner_id==owner)) is None
    finally:
        finish.set()
        with Session(test_engine) as db:db.execute(delete(User).where(User.id.in_([owner,other])));db.commit()


def test_interrupted_receipt_and_inactive_account(db_session,data,settings,monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    result=run(db_session,data,settings);identifier=uuid.UUID(result['id'])
    row=db_session.get(InterviewVoiceOperation,identifier)
    row.status='pending';row.deadline=voice.now()-timedelta(seconds=1);db_session.commit()
    assert voice.public(row)['status']=='unknown'
    def forbidden(*a):pytest.fail('Inactive account must not dispatch')
    monkeypatch.setattr(voice,'provider_for',forbidden)
    data.owner.is_active=False;db_session.commit()
    with pytest.raises(HTTPException):run(db_session,data,settings)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            row.transcript='Late worker result';db_session.flush()
    db_session.delete(data.owner);db_session.commit()
    assert db_session.get(InterviewVoiceOperation,identifier) is None


def test_speech_output_bound_and_cleanup(settings):
    def oversized(request):return httpx.Response(200,content=b'x'*1_000_001)
    client=OpenAI(api_key='offline-placeholder',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(oversized)))
    with pytest.raises(SpeechFailure):OpenAISpeechProvider(settings,client).speak('Synthetic question?')
    assert client.is_closed()


def test_offline_plan_and_independent_defaults(settings):
    from decimal import Decimal
    from app.evaluation.voice_plan import build_plan
    plan=build_plan()
    assert plan['live_requests_sent']==0 and plan['planned_live_requests']==2
    assert Decimal(plan['estimated_budget_usd'])==Decimal('0.002035')
    before=(settings.JOBPILOT_AI_PROVIDER,settings.JOBPILOT_PACK_MODEL,settings.JOBPILOT_INTERVIEW_MODEL)
    voice.configuration(settings)
    assert before==(settings.JOBPILOT_AI_PROVIDER,settings.JOBPILOT_PACK_MODEL,settings.JOBPILOT_INTERVIEW_MODEL)
    provider=OpenAISpeechProvider(settings.model_copy(update={'JOBPILOT_VOICE_API_KEY':'offline-placeholder'}))
    try:
        assert provider.client.max_retries==0
        assert str(provider.client.base_url)=='https://api.openai.com/v1/'
    finally:provider.client.close()


def test_voice_without_consent_never_calls_provider(db_session,data,settings,monkeypatch):
    from fastapi import HTTPException
    grant_consent(db_session,data.owner.id,'ai_voice',allowed=False)  # Revoke the fixture grant.
    def forbidden(*a):pytest.fail('Speech provider must not be called without consent')
    monkeypatch.setattr(voice,'provider_for',forbidden)
    with pytest.raises(HTTPException) as error:
        run(db_session,data,settings)
    assert error.value.status_code==403
    assert db_session.get(AIUsage,data.owner.id).requests==1  # Only the interview advance; no voice op.
    assert db_session.scalar(select(InterviewVoiceOperation.id).where(InterviewVoiceOperation.owner_id==data.owner.id)) is None


def test_revoked_voice_consent_blocks_further_speech(db_session,data,settings,monkeypatch):
    from fastapi import HTTPException
    calls=[]
    class Recorder(SyntheticSpeechProvider):
        def transcribe(self,audio):calls.append(1);return super().transcribe(audio)
    monkeypatch.setattr(voice,'provider_for',lambda s:Recorder())
    first=run(db_session,data,settings)
    assert first['status']=='succeeded' and len(calls)==1
    grant_consent(db_session,data.owner.id,'ai_voice',allowed=False)  # Revoked mid-session.
    with pytest.raises(HTTPException) as error:
        run(db_session,data,settings,key=uuid.uuid4())
    assert error.value.status_code==403
    assert len(calls)==1  # No further speech request after revocation.


def test_consent_revoked_after_voice_reservation_finalizes_receipt(db_session,data,settings,monkeypatch):
    from fastapi import HTTPException
    from app.models import UsageReservation
    original_reserve=voice.ai_usage.reserve
    original_provider_for=voice.provider_for
    reserved={}
    provider_calls=[]
    def revoke_after_reservation(*args,**kwargs):
        token=original_reserve(*args,**kwargs);reserved['token']=token
        grant_consent(db_session,data.owner.id,'ai_voice',allowed=False)
        return token
    def forbidden_provider(*args):
        provider_calls.append(1)
        return SyntheticSpeechProvider()
    monkeypatch.setattr(voice.ai_usage,'reserve',revoke_after_reservation)
    monkeypatch.setattr(voice,'provider_for',forbidden_provider)
    key=uuid.uuid4()
    with pytest.raises(HTTPException) as error:
        run(db_session,data,settings,key=key)
    assert error.value.status_code==403 and provider_calls==[]
    receipt=db_session.scalar(select(InterviewVoiceOperation).where(
        InterviewVoiceOperation.owner_id==data.owner.id,
        InterviewVoiceOperation.request_key==key))
    assert receipt.status=='failed' and receipt.outcome=='consent_or_account_denied'
    usage=db_session.get(AIUsage,data.owner.id)
    assert usage.active_token is None and usage.active_until is None
    assert db_session.get(UsageReservation,reserved['token']).released_at is not None

    grant_consent(db_session,data.owner.id,'ai_voice')
    assert run(db_session,data,settings,key=key)['status']=='failed'
    assert provider_calls==[]  # Same key returns the terminal receipt without redispatch.
    monkeypatch.setattr(voice.ai_usage,'reserve',original_reserve)
    monkeypatch.setattr(voice,'provider_for',original_provider_for)
    assert run(db_session,data,settings,key=uuid.uuid4())['status']=='succeeded'
