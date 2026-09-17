import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_password, hash_token, create_access_token
from app.models import User, AccountToken, AccountThrottle, RefreshToken
from app.services import account_service as service, account_mail, auth_service

PASSWORD = "synthetic-password-for-accounts"


@pytest.fixture
def settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "JOBPILOT_REGISTRATION", "invite-only")
    monkeypatch.setattr(settings, "JOBPILOT_ACCOUNT_APP_URL", "http://localhost:3010")
    monkeypatch.setattr(account_mail, "configured", lambda settings: None)
    messages = []
    monkeypatch.setattr(account_mail, "send", lambda s, email, purpose, token=None: messages.append((email,purpose,token)))
    return settings, messages


@pytest.fixture
def api(client, db_session):
    def dependency():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise
    client.app.dependency_overrides[get_db] = dependency
    yield client
    client.app.dependency_overrides.clear()


def test_invitation_registration_verification_and_privilege_boundary(api, db_session, settings):
    s,messages=settings
    email=f"account-{uuid.uuid4()}@example.com"
    invite=service.invitation(db_session,email,1)
    assert db_session.get(AccountToken,hash_token(invite)).token_hash != invite
    payload={"email":email,"password":PASSWORD,"invitation":invite}
    assert api.post('/api/account/register',json={**payload,'is_admin':True}).status_code==422
    assert api.post('/api/account/register',json=payload).status_code==200
    user=db_session.scalar(select(User).where(User.email==email))
    assert not user.email_verified and user.onboarding_step=='profile'
    assert not hasattr(user,'is_admin')
    assert api.post('/api/auth/login',json={"email":email,"password":PASSWORD}).status_code==401
    token=messages[-1][2]
    assert api.post('/api/account/verify',json={'token':token}).status_code==200
    assert api.post('/api/account/verify',json={'token':token}).status_code==400
    assert api.post('/api/auth/login',json={"email":email,"password":PASSWORD}).status_code==200
    assert api.post('/api/account/register',json=payload).status_code==400


def test_modes_expiry_bound_email_and_delivery_failure(db_session, settings, monkeypatch):
    s,messages=settings
    email=f"account-{uuid.uuid4()}@example.com"
    raw=service.invitation(db_session,email,1)
    with pytest.raises(HTTPException): service.register(db_session,s,'other@example.com',PASSWORD,raw)
    db_session.rollback()
    row=db_session.get(AccountToken,hash_token(raw));row.expires_at=service.now()-timedelta(seconds=1);db_session.commit()
    with pytest.raises(HTTPException): service.register(db_session,s,email,PASSWORD,raw)
    db_session.rollback()
    monkeypatch.setattr(s,'JOBPILOT_REGISTRATION','closed')
    with pytest.raises(HTTPException) as error: service.register(db_session,s,email,PASSWORD,None)
    assert error.value.status_code==403
    monkeypatch.setattr(s,'JOBPILOT_REGISTRATION','public')
    def failure(*args): raise HTTPException(503,'Not accepted')
    monkeypatch.setattr(account_mail,'send',failure)
    with pytest.raises(HTTPException): service.register(db_session,s,email,PASSWORD,None)
    db_session.rollback()
    assert db_session.scalar(select(User).where(User.email==email)) is None


def test_reset_enumeration_replay_invalidates_access_and_refresh(api,db_session,settings):
    s,messages=settings
    user=User(email=f"reset-{uuid.uuid4()}@example.com",password_hash=hash_password(PASSWORD));db_session.add(user);db_session.commit()
    access,refresh=auth_service.issue_session(db_session,user=user)
    known=api.post('/api/account/request/reset',json={'email':user.email})
    raw=messages[-1][2]
    unknown=api.post('/api/account/request/reset',json={'email':'unknown@example.com'})
    assert known.status_code==unknown.status_code==200 and known.json()==unknown.json()
    assert messages[-1][2] is None
    assert api.post('/api/account/reset',json={'token':raw,'password':PASSWORD+'new'}).status_code==200
    assert api.get('/api/auth/me',headers={'Authorization':'Bearer '+access}).status_code==401
    with pytest.raises(auth_service.InvalidRefreshTokenError): auth_service.rotate_refresh(db_session,presented=refresh)
    assert api.post('/api/account/reset',json={'token':raw,'password':PASSWORD}).status_code==400
    assert api.post('/api/auth/login',json={'email':user.email,'password':PASSWORD+'new'}).status_code==200


def test_throttle_and_onboarding_isolation(api,db_session,settings):
    users=[User(email=f"onboard-{uuid.uuid4()}@example.com",password_hash=hash_password(PASSWORD),onboarding_step='profile') for _ in range(2)]
    db_session.add_all(users);db_session.commit()
    headers={'Authorization':'Bearer '+create_access_token(users[0].id)}
    assert api.patch('/api/account/onboarding',headers=headers,json={'step':'cv','user_id':str(users[1].id)}).status_code==422
    assert api.patch('/api/account/onboarding',headers=headers,json={'step':'cv'}).status_code==200
    assert api.get('/api/account/onboarding',headers=headers).json()['step']=='cv'
    assert users[1].onboarding_step=='profile'
    for _ in range(5): assert api.post('/api/account/request/reset',json={'email':'throttled@example.com'}).status_code==200
    assert api.post('/api/account/request/reset',json={'email':'throttled@example.com'}).status_code==429


def test_concurrent_invitation_single_acceptance(test_engine, settings):
    s,messages=settings
    email=f"concurrent-{uuid.uuid4()}@example.com"
    with Session(test_engine) as db: raw=service.invitation(db,email,1)
    def accept():
        with Session(test_engine) as db:
            try:
                service.register(db,s,email,PASSWORD,raw)
                return 200
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:accept(),range(2)))
        assert sorted(results)==[200,400]
    finally:
        with Session(test_engine) as db:
            db.execute(delete(AccountToken).where(AccountToken.email==email))
            db.execute(delete(User).where(User.email==email));db.commit()


def test_transport_fails_closed_without_network():
    s=get_settings().model_copy(update={'JOBPILOT_ACCOUNT_APP_URL':'https://app.example.com','JOBPILOT_ACCOUNT_MAIL_TRANSPORT':'disabled'})
    with pytest.raises(HTTPException) as error: account_mail.configured(s)
    assert error.value.status_code==503
    s.JOBPILOT_ACCOUNT_APP_URL='https://attacker.example.com/#fragment'
    with pytest.raises(HTTPException): account_mail.configured(s)


def test_concurrent_reset_consumes_once(test_engine):
    email=f"concurrent-reset-{uuid.uuid4()}@example.com"
    with Session(test_engine) as db:
        user=User(email=email,password_hash=hash_password(PASSWORD));db.add(user);db.flush()
        raw=service.token(db,'reset',email,user.id);db.commit()
    def reset():
        with Session(test_engine) as db:
            try:
                service.finish(db,raw,'reset',PASSWORD+'new')
                return 200
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:reset(),range(2)))
        assert sorted(results)==[200,400]
        with Session(test_engine) as db: assert db.scalar(select(User).where(User.email==email)).session_version==1
    finally:
        with Session(test_engine) as db:
            db.execute(delete(User).where(User.email==email));db.commit()


def test_expired_reset_and_validation_never_echo_secrets(api,db_session,settings):
    user=User(email=f"expired-{uuid.uuid4()}@example.com",password_hash=hash_password(PASSWORD));db_session.add(user);db_session.flush()
    raw=service.token(db_session,'reset',user.email,user.id,hours=-1);db_session.commit()
    assert api.post('/api/account/reset',json={'token':raw,'password':PASSWORD}).status_code==400
    response=api.post('/api/account/reset',json={'token':raw,'password':'secret'})
    assert response.status_code==422 and raw not in response.text and 'secret' not in response.text
    assert user.session_version==0


def test_smtp_acceptance_rejection_and_safe_errors(monkeypatch, caplog):
    s=get_settings().model_copy(update={'JOBPILOT_ACCOUNT_APP_URL':'https://app.example.com',
      'JOBPILOT_ACCOUNT_MAIL_TRANSPORT':'smtp','JOBPILOT_ACCOUNT_SMTP_HOST':'smtp.example.com',
      'JOBPILOT_ACCOUNT_MAIL_FROM':'accounts@example.com','JOBPILOT_ACCOUNT_SMTP_USER':'',
      'JOBPILOT_ACCOUNT_SMTP_PASSWORD':'credential-must-not-leak'})
    calls=[]
    class SMTP:
        rejected=False
        def __init__(self,*args,**kwargs): assert kwargs['timeout']==10
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def send_message(self,message):
            calls.append(message)
            if self.rejected: raise RuntimeError('provider-body-with-secret')
            return {}
    monkeypatch.setattr(account_mail.smtplib,'SMTP_SSL',SMTP)
    account_mail.send(s,'synthetic@example.com','reset','secret-token')
    assert 'https://app.example.com/reset-password#token=secret-token' in calls[0].get_content()
    SMTP.rejected=True
    with pytest.raises(HTTPException) as error: account_mail.send(s,'synthetic@example.com','reset','secret-token')
    assert error.value.status_code==503
    assert 'provider-body' not in error.value.detail
    assert 'secret' not in caplog.text


def test_invite_cli_bounds_and_private_output(db_session,monkeypatch,tmp_path,capsys):
    from contextlib import nullcontext
    from app import cli
    s=get_settings()
    monkeypatch.setattr(s,'JOBPILOT_ACCOUNT_APP_URL','http://localhost:3010')
    monkeypatch.setattr(cli,'SessionLocal',lambda:nullcontext(db_session))
    path=tmp_path/'invitation.txt'
    assert cli.main(['invite','--email','invited@example.com','--hours','2','--output',str(path)])==0
    raw=path.read_text().split('#token=')[1].strip()
    assert raw not in capsys.readouterr().out
    assert db_session.get(AccountToken,hash_token(raw)).email=='invited@example.com'
    with pytest.raises(FileExistsError): cli.main(['invite','--email','invited@example.com','--output',str(path)])
    with pytest.raises(SystemExit): cli.main(['invite','--email','invited@example.com','--hours','169','--output',str(tmp_path/'bad.txt')])
    assert not (tmp_path/'bad.txt').exists()


def test_test_transport_and_fixture_endpoints_are_guarded(client,monkeypatch):
    s=get_settings()
    monkeypatch.setattr(s,'E2E_TEST_MODE',False)
    assert client.post('/api/e2e/account-fixture').status_code==404
    assert client.post('/api/e2e/account-message',json={'ticket':'x'*32}).status_code==404
    guarded=s.model_copy(update={'JOBPILOT_ACCOUNT_APP_URL':'http://localhost:3010','JOBPILOT_ACCOUNT_MAIL_TRANSPORT':'test'})
    with pytest.raises(HTTPException): account_mail.configured(guarded)


def test_public_registration_duplicate_preserves_account(api,db_session,settings,monkeypatch):
    s,messages=settings
    monkeypatch.setattr(s,'JOBPILOT_REGISTRATION','public')
    email=f"public-{uuid.uuid4()}@example.com"
    first=api.post('/api/account/register',json={'email':email,'password':PASSWORD})
    user=db_session.scalar(select(User).where(User.email==email))
    original_hash=user.password_hash
    duplicate=api.post('/api/account/register',json={'email':email,'password':PASSWORD+'changed'})
    assert first.status_code==duplicate.status_code==200 and first.json()==duplicate.json()
    db_session.refresh(user)
    assert user.password_hash==original_hash and not user.email_verified
    assert messages[-1][2] is None


def test_recovery_delivery_failure_is_generic_for_unknown_accounts(api,db_session,settings,monkeypatch):
    s,messages=settings
    user=User(email=f"delivery-{uuid.uuid4()}@example.com",password_hash=hash_password(PASSWORD));db_session.add(user);db_session.commit()
    def failure(*args): raise HTTPException(503,'Account email was not confirmed accepted; try again later')
    monkeypatch.setattr(account_mail,'send',failure)
    known=api.post('/api/account/request/reset',json={'email':user.email})
    unknown=api.post('/api/account/request/reset',json={'email':'no-account@example.com'})
    assert known.status_code==unknown.status_code==503 and known.json()==unknown.json()
    assert db_session.scalar(select(AccountToken).where(AccountToken.user_id==user.id)) is None
