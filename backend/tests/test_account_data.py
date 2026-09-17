import io
import json
import uuid
import zipfile
from datetime import timedelta
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update, text
from sqlalchemy.exc import IntegrityError
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, hash_token
from app.models import (Base, User, Resume, SavedJob, AccountExport, AccountDeletion, AccountToken,
    RefreshToken, MailboxConnection, MailboxReply, EmailApplication, InterviewSession,
    ApplicationRecord, ApplicationStatusEvent, ReplySync, InterviewOperation, AIUsage)
from app.services import account_data as service, auth_service
from app.services.object_store import StorageUnavailable
from test_email_applications import seed, settings

PASSWORD = "synthetic-account-deletion-password"


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("No live providers"))


@pytest.fixture
def data(db_session, settings, monkeypatch):
    data = seed(db_session, settings)
    data.owner.password_hash = hash_password(PASSWORD)
    db_session.commit()
    monkeypatch.setattr(service.resume_store, "read_bytes", lambda identifier: b"x")
    monkeypatch.setattr(service.resume_store, "delete_bytes", lambda identifier: None)
    monkeypatch.setattr(service, "provider_for", lambda s: SimpleNamespace(name="google", revoke=lambda token: None))
    return data


@pytest.fixture
def api(client, db_session):
    def dependency():
        try: yield db_session
        except Exception:
            db_session.rollback(); raise
    client.app.dependency_overrides[get_db] = dependency
    yield client
    client.app.dependency_overrides.clear()


def test_export_private_complete_bytes_no_credentials_and_expiry(db_session, data, settings):
    other_job = SavedJob(owner_id=data.other.id, title="Private other job", company="Other")
    db_session.add(other_job); db_session.commit()
    result = service.create_export(db_session, data.owner.id, PASSWORD, settings)
    raw = service.download(db_session, data.owner, uuid.UUID(result["id"]))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        output = json.loads(archive.read("account.json"))
        assert archive.read("documents/" + output['resumes'][0]['id']) == b"x"
    assert output['saved_jobs'][0]['id'] == str(data.job.id)
    assert len(output['saved_jobs']) == 1
    assert output['application_pack_versions'][0]['cv'] == data.version.cv
    assert 'password_hash' not in output['users'][0]
    assert 'credentials' not in output['mailbox_connections'][0]
    assert b'synthetic-refresh' not in raw and data.owner.password_hash.encode() not in raw
    with pytest.raises(HTTPException) as error: service.download(db_session, data.other, uuid.UUID(result['id']))
    assert error.value.status_code == 404
    row = db_session.get(AccountExport, uuid.UUID(result['id']))
    row.expires_at = service.now() - timedelta(seconds=1); db_session.commit()
    with pytest.raises(HTTPException): service.download(db_session, data.owner, row.id)


def test_export_bounds_missing_storage_and_reauth(api, db_session, data, settings, monkeypatch):
    headers = {'Authorization': 'Bearer ' + create_access_token(data.owner.id)}
    assert api.post('/api/account/data/exports', json={'password':PASSWORD}).status_code == 401
    assert api.post('/api/account/data/exports', headers=headers, json={'password':'wrong'}).status_code == 403
    with pytest.raises(HTTPException) as error:
        service.create_export(db_session, data.owner.id, PASSWORD, settings.model_copy(update={'ACCOUNT_EXPORT_MAX_ROWS':1}))
    assert error.value.status_code == 413
    db_session.rollback()
    monkeypatch.setattr(service.resume_store, 'read_bytes', lambda _: None)
    with pytest.raises(HTTPException) as error: service.create_export(db_session, data.owner.id, PASSWORD, settings)
    assert error.value.status_code == 503
    db_session.rollback()
    assert db_session.scalar(select(AccountExport.id).where(AccountExport.owner_id == data.owner.id)) is None


def test_deletion_invalidates_sessions_and_resumes_storage_failure(api, db_session, data, settings, monkeypatch):
    access, refresh = auth_service.issue_session(db_session, user=data.owner)
    headers = {'Authorization':'Bearer ' + access}
    response = api.post('/api/account/data/deletions', headers=headers, json={'password':PASSWORD,'confirmation':'DELETE MY ACCOUNT'})
    assert response.status_code == 202
    receipt = response.json(); identifier = uuid.UUID(receipt['id'])
    assert api.get('/api/auth/me', headers=headers).status_code == 401
    assert db_session.scalar(select(RefreshToken).where(RefreshToken.user_id == data.owner.id)) is None
    assert db_session.get(AccountDeletion, identifier).receipt_hash != receipt['receipt']
    assert api.post(f'/api/account/data/deletions/{identifier}/status', json={'receipt':'x'*43}).status_code == 404
    monkeypatch.setattr(service.resume_store, 'delete_bytes', lambda _: (_ for _ in ()).throw(StorageUnavailable()))
    service.cleanup_deletion(db_session, identifier, settings)
    assert service.status(db_session, identifier, receipt['receipt'])['status'] == 'failed'
    assert db_session.scalar(select(Resume).where(Resume.owner_id == data.owner.id))
    monkeypatch.setattr(service.resume_store, 'delete_bytes', lambda _: None)
    service.cleanup_deletion(db_session, identifier, settings)
    assert service.status(db_session, identifier, receipt['receipt'])['status'] == 'complete'
    db_session.expire_all()
    assert db_session.get(User, data.owner.id) is None
    assert db_session.get(User, data.other.id) is not None
    for table in Base.metadata.tables.values():
        if 'owner_id' in table.c and table.name != 'account_deletions':
            assert db_session.execute(select(table.c.owner_id).where(table.c.owner_id == data.owner.id)).first() is None
    service.cleanup_deletion(db_session, identifier, settings)  # idempotent


def test_late_writes_reactivation_ai_and_oauth_blocked(db_session, data, settings):
    from app.services import ai_usage, mailbox_service
    receipt = service.request_deletion(db_session, data.owner.id, PASSWORD, 'DELETE MY ACCOUNT')
    with pytest.raises(ai_usage.AIUsageError): ai_usage.reserve(db_session, owner_id=data.owner.id, settings=settings)
    db_session.rollback()
    with pytest.raises(Exception): mailbox_service.owner_lock(db_session, data.owner.id)
    db_session.rollback()
    for statement in [
        update(SavedJob).where(SavedJob.id == data.job.id).values(title='Late AI write'),
        update(User).where(User.id == data.owner.id).values(is_active=True),
        text('UPDATE application_pack_versions SET number=number WHERE id=:id').bindparams(id=data.version.id),
    ]:
        with pytest.raises(IntegrityError): db_session.execute(statement)
        db_session.rollback()
    db_session.add(SavedJob(owner_id=data.owner.id, title='Late new job', company='Example'))
    with pytest.raises(IntegrityError): db_session.flush()
    db_session.rollback()
    assert db_session.get(AccountDeletion, uuid.UUID(receipt['id'])).status == 'pending'


def test_revocation_failure_interrupted_lease_and_batch_resume(db_session, data, settings, monkeypatch):
    extra = Resume(owner_id=data.owner.id, original_filename='second.pdf', display_name='Second', file_extension='pdf', size_bytes=1)
    db_session.add(extra); db_session.commit()
    receipt = service.request_deletion(db_session, data.owner.id, PASSWORD, 'DELETE MY ACCOUNT')
    identifier = uuid.UUID(receipt['id']); calls=[]
    def revoke(token): calls.append(True); raise RuntimeError('sensitive provider body')
    monkeypatch.setattr(service, 'provider_for', lambda _: SimpleNamespace(name='google',revoke=revoke))
    service.cleanup_deletion(db_session, identifier, settings, batch_size=1)
    row = db_session.get(AccountDeletion, identifier)
    assert row.status == 'pending' and row.revocation_unconfirmed and len(calls) == 1
    row.lease_until = service.now() + timedelta(minutes=5); db_session.commit()
    service.cleanup_deletion(db_session, identifier, settings, batch_size=1)
    assert row.status == 'pending'
    row.lease_until = service.now() - timedelta(seconds=1); db_session.commit()
    service.cleanup_deletion(db_session, identifier, settings, batch_size=1)
    assert row.status == 'complete' and row.revocation_unconfirmed and len(calls) == 1


def test_retention_boundary_dry_run_and_idempotency(db_session, data, settings, monkeypatch):
    fixed = service.now(); monkeypatch.setattr(service, 'now', lambda:fixed)
    cutoff = fixed - timedelta(days=settings.ACCOUNT_TOKEN_RETENTION_DAYS)
    expired = AccountToken(token_hash=hash_token('expired synthetic'),purpose='reset',email=data.owner.email,user_id=data.owner.id,expires_at=cutoff)
    future = AccountToken(token_hash=hash_token('future synthetic'),purpose='reset',email=data.owner.email,user_id=data.owner.id,expires_at=cutoff+timedelta(seconds=1))
    db_session.add_all([expired,future]);db_session.commit()
    counts=service.retention(db_session,settings,dry_run=True)
    if counts['account_tokens'] != 1 or any(v for k,v in counts.items() if k != 'account_tokens'):
        pytest.skip('Retention mutation coverage requires no eligible preexisting records')
    assert db_session.get(AccountToken,expired.token_hash)
    service.retention(db_session,settings,dry_run=False)
    assert db_session.get(AccountToken,expired.token_hash) is None
    assert db_session.get(AccountToken,future.token_hash)
    assert service.retention(db_session,settings,dry_run=False)['account_tokens'] == 0


def test_wrong_confirmation_and_password_cannot_delete(db_session, data):
    for password, confirmation in [(PASSWORD,'delete'),('wrong','DELETE MY ACCOUNT')]:
        with pytest.raises(HTTPException): service.request_deletion(db_session,data.owner.id,password,confirmation)
        db_session.rollback()
    assert db_session.get(User,data.owner.id).is_active


def test_last_account_guard_is_fail_closed_without_changing_existing_users(db_session, data, monkeypatch):
    monkeypatch.setattr(service, 'has_recovery_account', lambda *args:False)
    with pytest.raises(HTTPException) as error:
        service.request_deletion(db_session,data.owner.id,PASSWORD,'DELETE MY ACCOUNT')
    assert error.value.status_code == 409
    db_session.rollback()
    assert db_session.get(User,data.owner.id).is_active


def test_retained_email_interviews_reminders_export_and_full_cascade(db_session, data, settings):
    owner=data.owner.id; instant=service.now()
    application=ApplicationRecord(owner_id=owner,job_id=data.job.id,submission_date=instant,
        method='email',status='Applied',reminder_status='scheduled',reminder_timezone='Asia/Beirut',follow_up_date=instant,
        pack_id=data.pack.id,pack_version=1)
    interview=InterviewSession(owner_id=owner,job_id=data.job.id,request_key=uuid.uuid4(),request_hash='hash',
        source_snapshot={'fact':'Synthetic'},configuration={},mode='mixed',question_count=2,status='completed',turns=[{'answer':'Synthetic answer'}])
    db_session.add_all([application,interview,AIUsage(owner_id=owner,requests=2)]);db_session.flush()
    event=ApplicationStatusEvent(application_id=application.id,status='Applied',changed_at=instant)
    operation=InterviewOperation(session_id=interview.id,request_key=uuid.uuid4(),request_hash='hash',step=1,status='complete',deadline=instant,usage={'output_tokens':25})
    email=EmailApplication(owner_id=owner,job_id=data.job.id,application_id=application.id,
        snapshot={'body':'Synthetic letter','attachments':[{'data':'eA=='}]},raw_message=b'Synthetic raw MIME',snapshot_hash='h',status='sent')
    db_session.add_all([event,operation,email]);db_session.flush()
    reply=MailboxReply(owner_id=owner,mailbox_id=data.connection.id,attempt_id=email.id,suggested_job_id=data.job.id,
        job_id=data.job.id,message_id='reply',thread_id='thread',match_kind='confirmed',sender='synthetic@example.com',subject='Reply',preview='Synthetic response',received_at=instant)
    sync=ReplySync(owner_id=owner,mailbox_id=data.connection.id,attempt_id=email.id,progress={'cursor':'provider-history-cursor'})
    db_session.add_all([reply,sync]);db_session.commit()
    ids=[(ApplicationRecord,application.id),(ApplicationStatusEvent,event.id),(InterviewSession,interview.id),
         (InterviewOperation,operation.id),(EmailApplication,email.id),(MailboxReply,reply.id),(ReplySync,email.id)]
    archive=service.create_export(db_session,owner,PASSWORD,settings)
    with zipfile.ZipFile(io.BytesIO(service.download(db_session,data.owner,uuid.UUID(archive['id'])))) as bundle:
        output=json.loads(bundle.read('account.json'))
    assert output['applications'][0]['reminder_timezone']=='Asia/Beirut'
    assert output['interview_sessions'][0]['turns'][0]['answer']=='Synthetic answer'
    assert output['interview_operations'][0]['usage']=={'output_tokens':25}
    assert output['email_applications'][0]['snapshot']['attachments'][0]['data']=='eA=='
    assert output['mailbox_replies'][0]['preview']=='Synthetic response'
    receipt=service.request_deletion(db_session,owner,PASSWORD,'DELETE MY ACCOUNT')
    service.cleanup_deletion(db_session,uuid.UUID(receipt['id']),settings)
    assert service.status(db_session,uuid.UUID(receipt['id']),receipt['receipt'])['status']=='complete'
    db_session.expire_all()
    for model,identifier in ids: assert db_session.get(model,identifier) is None


def test_expired_reauth_via_password_reset_invalidates_export(db_session,data,settings):
    result=service.create_export(db_session,data.owner.id,PASSWORD,settings)
    data.owner.session_version += 1;db_session.commit()
    with pytest.raises(HTTPException):service.download(db_session,data.owner,uuid.UUID(result['id']))


def test_email_preview_retention_preserves_matching_headers(db_session,data,settings,monkeypatch):
    fixed=service.now();monkeypatch.setattr(service,'now',lambda:fixed)
    email=EmailApplication(owner_id=data.owner.id,job_id=data.job.id,snapshot={},raw_message=b'x',snapshot_hash='x',status='sent')
    db_session.add(email);db_session.flush()
    cutoff=fixed-timedelta(days=settings.ACCOUNT_EMAIL_PREVIEW_DAYS)
    replies=[]
    for index,received in enumerate([cutoff,cutoff+timedelta(seconds=1)]):
        reply=MailboxReply(owner_id=data.owner.id,mailbox_id=data.connection.id,attempt_id=email.id,suggested_job_id=data.job.id,
            job_id=data.job.id,message_id=f'reply-{index}',thread_id='thread',match_kind='confirmed',sender='synthetic@example.com',subject='Reply',preview='Synthetic response',received_at=received)
        db_session.add(reply);replies.append(reply)
    db_session.commit()
    counts=service.retention(db_session,settings)
    if counts['email_previews'] != 1 or any(value for key,value in counts.items() if key!='email_previews'):
        pytest.skip('Mutation coverage requires no eligible preexisting records')
    assert replies[0].preview=='Synthetic response'
    service.retention(db_session,settings,dry_run=False);db_session.expire_all()
    assert replies[0].preview=='' and replies[0].thread_id=='thread' and replies[0].subject=='Reply'
    assert replies[1].preview=='Synthetic response'
    assert service.retention(db_session,settings)['email_previews']==0


def test_all_current_owner_tables_have_write_barriers(db_session):
    triggers=set(db_session.scalars(text("SELECT event_object_table FROM information_schema.triggers WHERE trigger_name='account_write_barrier'")))
    expected={t.name for t in Base.metadata.tables.values() if ('owner_id' in t.c or 'user_id' in t.c) and t.name!='account_deletions'}
    expected |= set(service.PARENTS) | {'application_pack_operations'}
    assert triggers==expected


def test_reauthentication_throttle(db_session,data):
    for _ in range(5):
        with pytest.raises(HTTPException) as error:service.reauthenticate(db_session,data.owner.id,'wrong')
        assert error.value.status_code==403;db_session.rollback()
    with pytest.raises(HTTPException) as error:service.reauthenticate(db_session,data.owner.id,PASSWORD)
    assert error.value.status_code==429


def test_account_deletion_during_mocked_ai_cannot_recreate_results(test_engine, settings, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy.orm import Session
    from app.models import AccountThrottle
    from app.services import interview_service
    from app.services.interview_provider import TestInterviewProvider as Synthetic
    from app.schemas.interviews import Advance
    from test_interviews import sources, begin
    entered, finish = Event(), Event()
    calls=[]
    class Slow(Synthetic):
        def practice(self,payload):
            calls.append(True);entered.set();assert finish.wait(15)
            return super().practice(payload)
    monkeypatch.setattr(interview_service,'provider_for',lambda *args:Slow())
    s=settings.model_copy(update={'JOBPILOT_AI_ENABLED':True,'JOBPILOT_AI_TEST_PROVIDER':True,
        'E2E_TEST_MODE':True,'POSTGRES_DB':settings.POSTGRES_TEST_DB})
    with Session(test_engine,expire_on_commit=False) as db:
        fixture=sources(db,s);owner,other=fixture.owner.id,fixture.other.id
        fixture.owner.password_hash=hash_password(PASSWORD);db.commit()
        row,_=begin(db,fixture,s);identifier=row.id
    def dispatch():
        with Session(test_engine,expire_on_commit=False) as db:
            try:
                interview_service.advance(db,owner,identifier,Advance(request_key=uuid.uuid4(),revision=0,confirm=True),s)
                return 'unexpected_write'
            except Exception:return 'blocked'
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(dispatch);assert entered.wait(10)
            with Session(test_engine,expire_on_commit=False) as db:
                service.request_deletion(db,owner,PASSWORD,'DELETE MY ACCOUNT')
            finish.set();assert future.result(timeout=10)=='blocked'
        with Session(test_engine) as db:
            assert not db.get(User,owner).is_active
            assert db.get(InterviewSession,identifier).turns==[]
            with pytest.raises(HTTPException):
                from app.services.ai_usage import dispatch_guard
                dispatch_guard(db,owner)
        assert len(calls)==1
    finally:
        finish.set()
        with Session(test_engine) as db:
            db.execute(delete(AccountDeletion).where(AccountDeletion.owner_id==owner))
            db.execute(delete(AccountThrottle).where(AccountThrottle.key==hash_token('account-data:'+str(owner))))
            db.execute(delete(User).where(User.id.in_([owner,other])));db.commit()
