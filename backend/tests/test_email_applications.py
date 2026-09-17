import base64
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from threading import Barrier, Lock
from types import SimpleNamespace

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import (ApplicationPack, ApplicationPackVersion, ApplicationRecord, CandidateProfile,
    EmailApplication, MailboxConnection, Resume, ResumeExtraction, SavedJob, User)
from app.schemas.email_applications import EmailApproval, EmailReview
from app.services import email_application_service as service, mailbox_service
from app.services.email_sender import GmailSender, SendResult, sender_for
from app.services.mailbox_provider import MailboxError, SCOPES, TestMailboxProvider as SyntheticOAuth, seal


@pytest.fixture(autouse=True)
def no_live_http(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("Live HTTP forbidden"))


@pytest.fixture()
def settings():
    return get_settings().model_copy(update={"JOBPILOT_MAILBOX_ENCRYPTION_KEY":Fernet.generate_key().decode(),
        "JOBPILOT_GOOGLE_CLIENT_ID":"test", "JOBPILOT_GOOGLE_CLIENT_SECRET":"test",
        "JOBPILOT_GOOGLE_REDIRECT_URI":"http://localhost:8000/api/mailboxes/oauth/callback",
        "JOBPILOT_MAILBOX_SETTINGS_URL":"http://localhost:3000/settings", "JOBPILOT_MAILBOX_TEST_PROVIDER":False})


class OAuth(SyntheticOAuth):
    name = "google"
    def refresh(self, token):
        return super().refresh(token).model_copy(update={"scope":"openid email " + SCOPES['send']})


class Sender:
    def __init__(self):
        self.calls=[]
        self.result=SendResult("sent", "gmail_accepted", 200, "message-1", "thread-1")
        self.lock=Lock()
    def send(self, token, raw):
        with self.lock:
            self.calls.append(raw)
        return self.result


def seed(db, settings):
    owner=User(email=f"email-{uuid.uuid4()}@example.com",password_hash="unused")
    other=User(email=f"email-other-{uuid.uuid4()}@example.com",password_hash="unused")
    db.add_all([owner,other]);db.flush()
    job=SavedJob(owner_id=owner.id,title="Backend engineer",company="Example")
    profile=CandidateProfile(owner_id=owner.id)
    resume=Resume(owner_id=owner.id,original_filename="cv.pdf",display_name="cv.pdf",file_extension="pdf",size_bytes=1)
    db.add_all([job,profile,resume]);db.flush()
    extraction=ResumeExtraction(resume_id=resume.id,status="succeeded",draft_text="Synthetic CV",reviewed_at=service.mailbox.now())
    db.add(extraction);db.flush()
    pack=ApplicationPack(owner_id=owner.id,job_id=job.id,profile_id=profile.id,resume_id=resume.id,extraction_id=extraction.id,
        idempotency_key=str(uuid.uuid4()),source_hash="test",source_snapshot={},status="ready",current_version=1,
        provider="test",model="test",prompt_version="test",deadline=service.mailbox.now())
    db.add(pack);db.flush()
    version=ApplicationPackVersion(pack_id=pack.id,number=1,approved_at=service.mailbox.now(),
        cv={"blocks":[{"kind":"paragraph","text":"Supported CV"}]},cover_letter={"blocks":[{"kind":"paragraph","text":"Supported letter"}]})
    connection=MailboxConnection(id=uuid.uuid4(),owner_id=owner.id,provider="google",subject=str(uuid.uuid4()),
        email="sender@example.com",capabilities=['send'],status="connected",expires_at=service.mailbox.now()+timedelta(hours=1))
    connection.credentials=seal(settings,mailbox_service.context(connection),{"refresh_token":"synthetic-refresh"})
    db.add_all([version,connection]);db.commit()
    return SimpleNamespace(owner=owner,other=other,job=job,pack=pack,version=version,connection=connection)


def payload(data, **changes):
    return EmailReview(mailbox_id=data.connection.id,pack_id=data.pack.id,pack_version=1,
        **({"recipient":"recruiter@example.com","confirm_recipient":"recruiter@example.com",
           "recipient_source":"Recruiter instructions https://example.com/job", "subject":"My application", "body":"Please review my attached application."}|changes))


def approval(row):
    return EmailApproval(snapshot_hash=row.snapshot_hash,confirm=True)


@pytest.fixture()
def setup(db_session,settings,monkeypatch):
    data=seed(db_session,settings)
    sender=Sender();provider=OAuth(settings)
    monkeypatch.setattr(service,'provider_for',lambda s:provider)
    monkeypatch.setattr(service,'sender_for',lambda s:sender)
    monkeypatch.setattr(service.pack_export,'render_document',lambda document,format:b'%PDF-synthetic-'+document['blocks'][0]['text'].encode())
    return data,sender,provider


def prepare(db,data,settings,**changes):
    return service.create_review(db,data.owner.id,data.job.id,payload(data,**changes),settings)


def dispatch(db,data,row,settings):
    return service.send(db,data.owner.id,data.job.id,row.id,approval(row),settings)


def test_review_is_not_send_and_exact_approved_attachment_bytes_are_dispatched(db_session,settings,setup):
    data,sender,_=setup
    row=prepare(db_session,data,settings)
    assert not sender.calls and row.approved_at is None
    before=bytes(row.raw_message)
    result=dispatch(db_session,data,row,settings)
    assert result.status=='sent' and result.provider_message_id=='message-1' and result.approved_hash==row.snapshot_hash
    assert sender.calls==[before]
    mime=BytesParser(policy=policy.default).parsebytes(sender.calls[0])
    assert mime['To']=='recruiter@example.com' and mime['From']=='sender@example.com'
    assert mime['Bcc'] is None and mime['Cc'] is None
    assert [p.get_payload(decode=True) for p in mime.iter_attachments()]==[base64.b64decode(a['data']) for a in row.snapshot['attachments']]
    app=db_session.get(ApplicationRecord,result.application_id)
    assert app.owner_id==data.owner.id and app.status=='Applied' and app.cv_snapshot==data.version.cv
    assert dispatch(db_session,data,row,settings).status=='sent' and len(sender.calls)==1
    with pytest.raises(service.PackError):prepare(db_session,data,settings)


@pytest.mark.parametrize('result',[SendResult('failed','gmail_rejected',403),SendResult('unknown','transport_or_response_uncertain'),SendResult('simulated','synthetic_acceptance_no_email',200)])
def test_rejection_timeout_and_synthetic_never_mark_submitted(db_session,settings,setup,result):
    data,sender,_=setup;sender.result=result
    row=prepare(db_session,data,settings)
    assert dispatch(db_session,data,row,settings).status==result.status
    assert not db_session.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id==data.job.id))
    dispatch(db_session,data,row,settings)
    assert len(sender.calls)==1
    if result.status in ('unknown','simulated'):
        with pytest.raises(service.PackError):prepare(db_session,data,settings)


def test_changed_message_replaces_review_and_old_approval_cannot_send(db_session,settings,setup):
    data,sender,_=setup
    old=prepare(db_session,data,settings)
    new=prepare(db_session,data,settings,subject='Changed subject')
    assert old.id!=new.id and old.snapshot_hash!=new.snapshot_hash
    assert dispatch(db_session,data,old,settings).status=='cancelled' and not sender.calls
    with pytest.raises(service.PackError):
        service.send(db_session,data.owner.id,data.job.id,new.id,approval(old),settings)
    assert not sender.calls


@pytest.mark.parametrize('change',['pack_content','pack_approval','mailbox_permission','revoked','partial_scope','disconnected'])
def test_preflight_rechecks_approval_and_permissions(db_session,settings,setup,change):
    data,sender,provider=setup
    row=prepare(db_session,data,settings)
    if change=='pack_content':data.version.cv={'blocks':[{'kind':'paragraph','text':'Changed'}]}
    if change=='pack_approval':data.version.approved_at=None
    if change=='mailbox_permission':data.connection.capabilities=['read_replies']
    if change=='disconnected':data.connection.status='disconnected'
    if change=='revoked':
        def fail(token):raise MailboxError('reconnect_required',409)
        provider.refresh=fail
    if change=='partial_scope':provider.refresh=lambda token:provider.exchange('test','test').model_copy(update={'scope':'openid email'})
    db_session.commit()
    assert dispatch(db_session,data,row,settings).status=='failed' and not sender.calls
    assert not db_session.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id==data.job.id))


def test_owner_and_job_isolation_for_review_send_and_download(client,db_session,settings,setup):
    data,sender,_=setup
    row=prepare(db_session,data,settings)
    client.app.dependency_overrides[get_db]=lambda:db_session
    client.app.dependency_overrides[get_settings]=lambda:settings
    headers={'Authorization':'Bearer '+create_access_token(data.other.id)}
    base=f'/api/jobs/{data.job.id}/email-applications'
    try:
        for path in ('',f'/{row.id}',f'/{row.id}/attachments/0'):
            assert client.get(base+path,headers=headers).status_code==404
        assert client.post(base,json=payload(data).model_dump(mode='json'),headers=headers).status_code==404
        assert client.post(base+f'/{row.id}/send',json=approval(row).model_dump(),headers=headers).status_code==404
        assert client.post(base+f'/{row.id}/cancel',headers=headers).status_code==404
        data.connection.owner_id=data.other.id;db_session.commit()
        with pytest.raises(MailboxError):prepare(db_session,data,settings)
        assert not sender.calls
    finally:client.app.dependency_overrides.clear()


@pytest.mark.parametrize('field,value',[('subject','Hello\r\nBcc: stolen@example.com'),('recipient','a@example.com\n'),
    ('body','\x00'),('recipient','a@example.com, b@example.com'),('confirm_recipient','other@example.com'),('subject',' ')])
def test_unsafe_headers_and_unconfirmed_recipient_rejected(field,value):
    with pytest.raises(ValidationError):
        EmailReview(mailbox_id=uuid.uuid4(),pack_id=uuid.uuid4(),pack_version=1,
            **({'recipient':'a@example.com','confirm_recipient':'a@example.com','recipient_source':'manual source','subject':'hello','body':'body'}|{field:value}))


def test_attachment_size_and_snapshot_immutability(db_session,settings,setup,monkeypatch):
    data,sender,_=setup
    row=prepare(db_session,data,settings)
    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(update(EmailApplication).where(EmailApplication.id==row.id).values(raw_message=b'changed'))
    monkeypatch.setattr(service,'MAX_ATTACHMENT_BYTES',1)
    with pytest.raises(service.PackError):prepare(db_session,data,settings)
    assert not sender.calls


@pytest.mark.parametrize('invalid',['unapproved','other_owner_pack','other_job_pack','other_owner_mailbox','no_send'])
def test_invalid_review_sources_fail_closed(db_session,settings,setup,invalid):
    data,sender,_=setup
    if invalid=='unapproved':data.version.approved_at=None
    if invalid=='other_owner_pack':data.pack.owner_id=data.other.id
    if invalid=='other_job_pack':
        job=SavedJob(owner_id=data.owner.id,title='Another role',company='Example');db_session.add(job);db_session.flush();data.pack.job_id=job.id
    if invalid=='other_owner_mailbox':data.connection.owner_id=data.other.id
    if invalid=='no_send':data.connection.capabilities=['read_replies']
    db_session.commit()
    with pytest.raises((service.PackError,MailboxError)):prepare(db_session,data,settings)
    assert not sender.calls and not db_session.scalar(select(EmailApplication).where(EmailApplication.job_id==data.job.id))


def test_review_api_returns_only_preview_and_exact_attachment_downloads(client,db_session,settings,setup):
    data,sender,_=setup
    client.app.dependency_overrides[get_db]=lambda:db_session
    client.app.dependency_overrides[get_settings]=lambda:settings
    headers={'Authorization':'Bearer '+create_access_token(data.owner.id)}
    base=f'/api/jobs/{data.job.id}/email-applications'
    try:
        response=client.post(base,headers=headers,json=payload(data).model_dump(mode='json'))
        assert response.status_code==200
        body=response.json()
        assert body['status']=='review' and body['approved_at'] is None
        assert 'raw_message' not in response.text and 'synthetic-refresh' not in response.text
        row=db_session.get(EmailApplication,uuid.UUID(body['id']))
        for index,a in enumerate(row.snapshot['attachments']):
            download=client.get(base+f'/{row.id}/attachments/{index}',headers=headers)
            assert download.content==base64.b64decode(a['data'])
            assert download.headers['cache-control']=='no-store'
        altered=approval(row).model_dump()|{'subject':'tampered'}
        assert client.post(base+f'/{row.id}/send',headers=headers,json=altered).status_code==422
        denied=client.post(base+f'/{row.id}/send',headers=headers,json={'confirm':False,'snapshot_hash':row.snapshot_hash})
        assert denied.status_code==422 and not sender.calls
    finally:client.app.dependency_overrides.clear()


def test_missing_configuration_never_uses_a_synthetic_fallback(settings):
    settings.JOBPILOT_GOOGLE_CLIENT_SECRET=''
    with pytest.raises(MailboxError):sender_for(settings)


@pytest.mark.parametrize('code',[200,400,401,403,429,500])
def test_actual_gmail_wire_and_status_mapping(code):
    calls=[]
    def handler(request):
        calls.append(request)
        assert str(request.url)=='https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
        assert base64.urlsafe_b64decode(json.loads(request.content)['raw'])==b'exact approved MIME'
        return httpx.Response(code,json={'id':'provider-1','threadId':'thread-1','error':{'message':'unrestricted secret'}})
    result=GmailSender(httpx.MockTransport(handler)).send('private-token',b'exact approved MIME')
    assert result.status==('sent' if code==200 else 'unknown' if code==500 else 'failed')
    assert len(calls)==1 and 'secret' not in repr(result) and 'private-token' not in repr(result)


def test_timeout_after_dispatch_never_retries_and_missing_id_is_unknown():
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('sensitive body and credentials')
    result=GmailSender(httpx.MockTransport(handler)).send('private',b'private body')
    assert result.status=='unknown' and len(calls)==1 and 'sensitive' not in repr(result)
    assert GmailSender(httpx.MockTransport(lambda r:httpx.Response(200,json={}))).send('private',b'x').status=='unknown'


def test_sender_test_guard_and_no_fallback(settings):
    settings.JOBPILOT_MAILBOX_TEST_PROVIDER=True;settings.E2E_TEST_MODE=False
    with pytest.raises(MailboxError):sender_for(settings)
    settings.E2E_TEST_MODE=True;settings.POSTGRES_DB=settings.POSTGRES_TEST_DB
    assert sender_for(settings).send('test',b'test').status=='simulated'


def test_crashed_dispatch_remains_unknown_and_cannot_resend(db_session,settings,setup):
    data,sender,_=setup
    row=prepare(db_session,data,settings)
    snapshot_hash=row.snapshot_hash
    row.status='sending';row.dispatch_at=mailbox_service.now()-timedelta(minutes=3);row.approved_at=mailbox_service.now();row.approved_hash=snapshot_hash
    db_session.commit()
    assert service.public(dispatch(db_session,data,row,settings))['status']=='unknown' and not sender.calls
    with pytest.raises(service.PackError):prepare(db_session,data,settings)


def test_concurrent_send_claims_dispatch_once(test_engine,settings,monkeypatch):
    with Session(test_engine) as db:
        data=seed(db,settings)
        owner_id,other_id,job_id=data.owner.id,data.other.id,data.job.id
        sender=Sender()
        monkeypatch.setattr(service,'provider_for',lambda s:OAuth(settings))
        monkeypatch.setattr(service,'sender_for',lambda s:sender)
        monkeypatch.setattr(service.pack_export,'render_document',lambda *args:b'%PDF-synthetic')
        row=prepare(db,data,settings);attempt_id=row.id;body=approval(row)
    barrier=Barrier(2)
    def submit():
        with Session(test_engine) as db:
            barrier.wait()
            return service.send(db,owner_id,job_id,attempt_id,body,settings).status
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:submit(),range(2)))
        assert all(s in ('sending','sent') for s in results) and len(sender.calls)==1
        with Session(test_engine) as db:
            assert db.get(EmailApplication,attempt_id).status=='sent'
            assert len(db.scalars(select(ApplicationRecord).where(ApplicationRecord.job_id==job_id)).all())==1
    finally:
        with Session(test_engine) as db:
            db.execute(delete(User).where(User.id.in_([owner_id,other_id])))
            db.commit()  # Only this test's newly created users and their rows.
