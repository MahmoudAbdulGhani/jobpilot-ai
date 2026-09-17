import json
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import User, MailboxConnection, MailboxOAuthState
from app.services import mailbox_service as service
from app.services import mailbox_provider as provider
from app.api.routes import mailboxes


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("Live provider HTTP forbidden"))


@pytest.fixture()
def settings():
    return get_settings().model_copy(update={"JOBPILOT_GOOGLE_CLIENT_ID":"synthetic-client",
        "JOBPILOT_GOOGLE_CLIENT_SECRET":"synthetic-secret", "JOBPILOT_MAILBOX_ENCRYPTION_KEY":Fernet.generate_key().decode(),
        "JOBPILOT_GOOGLE_REDIRECT_URI":"http://testserver/api/mailboxes/oauth/callback",
        "JOBPILOT_MAILBOX_SETTINGS_URL":"http://localhost:3000/settings", "JOBPILOT_MAILBOX_TEST_PROVIDER":False})


class Fake(provider.TestMailboxProvider):
    name = "google"
    calls = None
    denied_scope = False
    fail_refresh = False
    fail_revoke = False
    def __init__(self, settings): super().__init__(settings); self.calls=[]
    def exchange(self, code, verifier):
        self.calls.append("exchange")
        if code == "bad": raise provider.MailboxError()
        token=super().exchange(code, verifier)
        if self.denied_scope: token.scope="openid email"
        return token
    def identity(self, token): self.calls.append("identity");return super().identity(token)
    def refresh(self, token):
        self.calls.append("refresh")
        if self.fail_refresh: raise provider.MailboxError("reconnect_required",409)
        return super().refresh(token)
    def revoke(self, token):
        self.calls.append("revoke")
        if self.fail_revoke: raise provider.MailboxError()


@pytest.fixture()
def setup(client, db_session, settings, monkeypatch):
    # Local TestClient's host is intentionally permitted only in this mocked fixture.
    monkeypatch.setattr(mailboxes, "validate_configuration", lambda s: None)
    fake=Fake(settings)
    monkeypatch.setattr(mailboxes, "provider_for", lambda s: fake)
    client.app.dependency_overrides[get_settings]=lambda:settings
    def db(): yield db_session
    client.app.dependency_overrides[get_db]=db
    users=[User(email=f"mailbox-{uuid.uuid4()}@example.test",password_hash="unused") for _ in range(2)]
    db_session.add_all(users);db_session.commit()
    headers=[{"Authorization":"Bearer "+create_access_token(u.id)} for u in users]
    yield client,db_session,fake,headers,users
    client.app.dependency_overrides.clear()


def begin(client, headers, caps=None, connection=None):
    response=client.post('/api/mailboxes/oauth/start',headers=headers,json={"capabilities":caps or [],"connection_id":connection})
    assert response.status_code==200
    assert "HttpOnly" in response.headers['set-cookie'] and "SameSite=lax" in response.headers['set-cookie']
    return response.json()['authorization_url']


def connect(client, headers, caps=None):
    callback=begin(client,headers,caps)
    response=client.get(callback,follow_redirects=False)
    assert response.status_code==303 and any('mailbox='+v in response.headers['location'] for v in ('connected','already_connected'))
    return client.get('/api/mailboxes',headers=headers).json()['items'][0]


def test_scopes_pkce_actual_wire_and_no_mail_endpoints(settings):
    settings.JOBPILOT_GOOGLE_REDIRECT_URI='http://localhost:8000/api/mailboxes/oauth/callback'
    provider.validate_configuration(settings)
    captured=[]
    def handler(request):
        captured.append(request)
        if str(request.url).endswith('/userinfo'): return httpx.Response(200,json={"sub":"stable-id","email":"a@example.com","email_verified":True})
        if str(request.url).endswith('/revoke'): return httpx.Response(200,content=b'')
        return httpx.Response(200,json={"access_token":"access","refresh_token":"refresh","expires_in":3600,"scope":"openid email "+provider.SCOPES['send'],"token_type":"Bearer"})
    p=provider.GoogleMailboxProvider(settings,httpx.MockTransport(handler))
    for caps in ([],['send'],['read_replies']):
        params=parse_qs(urlparse(p.authorize('state','v'*64,caps)).query)
        assert set(params['scope'][0].split())==provider.IDENTITY_SCOPES|{provider.SCOPES[c] for c in caps}
        assert params['code_challenge_method']==['S256'] and params['code_challenge'][0]!='v'*64
    token=p.exchange('code','v'*64);p.identity(token.access_token);p.refresh(token.refresh_token);p.revoke(token.refresh_token)
    body=parse_qs(captured[0].content.decode())
    assert body['code_verifier']==['v'*64] and body['client_secret']==['synthetic-secret']
    assert captured[1].headers['authorization']=='Bearer access'
    assert all('gmail.googleapis.com' not in str(r.url) for r in captured)
    assert len(captured)==4


def test_encryption_binds_owner_and_rejects_wrong_key(settings):
    encrypted=provider.seal(settings,'owner:a',{'refresh_token':'sensitive'})
    assert 'sensitive' not in encrypted
    assert provider.unseal(settings,'owner:a',encrypted)=={'refresh_token':'sensitive'}
    for owner in ('other','owner:b'):
        with pytest.raises(provider.MailboxError): provider.unseal(settings,owner,encrypted)
    settings.JOBPILOT_MAILBOX_ENCRYPTION_KEY=Fernet.generate_key().decode()
    with pytest.raises(provider.MailboxError): provider.unseal(settings,'owner:a',encrypted)


def test_connect_duplicate_owner_isolation_and_encrypted_storage(setup):
    client,db,fake,(first,second),users=setup
    row=connect(client,first,['send'])
    assert row['capabilities']==['send'] and fake.calls==['exchange','identity']
    stored=db.get(MailboxConnection,uuid.UUID(row['id']))
    assert 'synthetic-access' not in stored.credentials and 'synthetic-refresh' not in stored.credentials
    listing=client.get('/api/mailboxes',headers=first).text
    assert 'credentials' not in listing and 'token' not in listing
    assert client.get('/api/mailboxes',headers=second).json()['items']==[]
    for action in ('check','disconnect'):
        assert client.post(f"/api/mailboxes/{row['id']}/{action}",headers=second).status_code==404
    assert connect(client,first)['id']==row['id']
    assert client.get('/api/mailboxes',headers=first).json()['items'][0]['capabilities']==['send']
    other_callback=begin(client,second)
    assert 'account_unavailable' in client.get(other_callback,follow_redirects=False).headers['location']
    assert client.get('/api/mailboxes',headers=second).json()['items']==[]


def test_single_use_denial_expiry_browser_binding_and_failure(setup):
    client,db,fake,(first,_),_=setup
    callback=begin(client,first)
    cookie=client.cookies.get(mailboxes.COOKIE)
    client.cookies.clear()
    assert 'invalid_state' in client.get(callback,follow_redirects=False).headers['location']
    client.cookies.set(mailboxes.COOKIE,cookie)
    assert 'connected' in client.get(callback,follow_redirects=False).headers['location']
    client.cookies.set(mailboxes.COOKIE,cookie)
    assert 'invalid_state' in client.get(callback,follow_redirects=False).headers['location']
    client.cookies.clear()
    callback=begin(client,first).replace('code=synthetic','error=access_denied')
    count=len(fake.calls)
    assert 'denied' in client.get(callback,follow_redirects=False).headers['location'] and len(fake.calls)==count
    callback=begin(client,first)
    row=db.scalar(select(MailboxOAuthState));row.expires_at=service.now()-timedelta(seconds=1);db.commit()
    assert 'invalid_state' in client.get(callback,follow_redirects=False).headers['location']
    callback=begin(client,first).replace('code=synthetic','code=bad')
    assert 'provider_unavailable' in client.get(callback,follow_redirects=False).headers['location']
    assert db.scalar(select(MailboxOAuthState)).verifier is None


def test_partial_consent_refresh_and_revocation_states(setup):
    client,db,fake,(first,_),_=setup
    fake.denied_scope=True
    callback=begin(client,first,['send','read_replies'])
    assert 'partial' in client.get(callback,follow_redirects=False).headers['location']
    row=client.get('/api/mailboxes',headers=first).json()['items'][0]
    assert row['capabilities']==[]
    stored=db.get(MailboxConnection,uuid.UUID(row['id']));stored.expires_at=service.now()-timedelta(seconds=1);db.commit()
    assert client.get('/api/mailboxes',headers=first).json()['items'][0]['status']=='expired'
    assert client.post(f"/api/mailboxes/{row['id']}/check",headers=first).json()['status']=='connected'
    fake.fail_refresh=True
    assert client.post(f"/api/mailboxes/{row['id']}/check",headers=first).status_code==409
    assert client.get('/api/mailboxes',headers=first).json()['items'][0]['status']=='reconnect_required'
    assert db.get(MailboxConnection,uuid.UUID(row['id'])).credentials is None


@pytest.mark.parametrize('fail',[False,True])
def test_disconnect_erases_tokens_invalidates_pending_and_reports_revoke_failure(setup,fail):
    client,db,fake,(first,_),_=setup
    row=connect(client,first,['send']);callback=begin(client,first,['send'],row['id'])
    fake.fail_revoke=fail
    result=client.post(f"/api/mailboxes/{row['id']}/disconnect",headers=first)
    assert result.json()['status']==('revoke_failed' if fail else 'disconnected')
    assert result.json()['capabilities']==[] and db.get(MailboxConnection,uuid.UUID(row['id'])).credentials is None
    assert fake.calls[-1]=='revoke'
    assert 'invalid_state' in client.get(callback,follow_redirects=False).headers['location']


def test_test_provider_and_configuration_fail_closed(settings):
    with pytest.raises(provider.MailboxError): provider.provider_for(settings)
    settings.JOBPILOT_GOOGLE_REDIRECT_URI='http://localhost:8000/api/mailboxes/oauth/callback'
    settings.JOBPILOT_MAILBOX_TEST_PROVIDER=True;settings.E2E_TEST_MODE=False
    with pytest.raises(provider.MailboxError): provider.provider_for(settings)


def test_callback_query_redacted_before_access_logging():
    import asyncio
    captured=[]
    async def app(scope, receive, send): captured.append(scope)
    scope={'type':'http','path':mailboxes.COOKIE_PATH,'query_string':b'code=secret-code&state=secret-state'}
    asyncio.run(mailboxes.ScrubMailboxCallback(app)(scope,None,None))
    assert captured[0]['query_string']==b'' and scope['mailbox_callback']['code']==['secret-code']


def test_access_logger_filter_hides_callback_secrets():
    import logging
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s %s %s %s %s',
        ('client','GET',mailboxes.COOKIE_PATH+'?code=do-not-log&state=private','1.1',303),None)
    assert mailboxes.MailboxAccessLogFilter().filter(record)
    assert 'do-not-log' not in record.getMessage() and 'private' not in record.getMessage()


def test_reconnect_wrong_account_and_cross_owner_start_rejected(setup):
    client,db,fake,(first,second),_=setup
    row=connect(client,first)
    assert client.post('/api/mailboxes/oauth/start',headers=second,json={'connection_id':row['id']}).status_code==404
    callback=begin(client,first,['send'],row['id'])
    fake.identity=lambda token:provider.Identity(sub='different',email='different@example.com',email_verified=True)
    assert 'account_mismatch' in client.get(callback,follow_redirects=False).headers['location']
    assert client.get('/api/mailboxes',headers=first).json()['items'][0]['capabilities']==[]


def test_disconnect_during_exchange_cannot_resurrect_connection(setup):
    client,db,fake,(first,_),users=setup
    row=connect(client,first);callback=begin(client,first,['send'],row['id'])
    original=fake.exchange
    def exchange(code, verifier):
        token=original(code,verifier)
        service.disconnect(db,users[0].id,uuid.UUID(row['id']),fake.settings,fake)
        return token
    fake.exchange=exchange
    assert 'invalid_state' in client.get(callback,follow_redirects=False).headers['location']
    stored=db.get(MailboxConnection,uuid.UUID(row['id']))
    assert stored.status=='disconnected' and stored.credentials is None


@pytest.mark.parametrize('mode',['denied_identity','invalid_grant','timeout','malformed'])
def test_provider_errors_are_sanitized_without_retry(settings,mode):
    calls=[]
    def handler(request):
        calls.append(request)
        if mode=='timeout':raise httpx.ReadTimeout('sensitive access-token secret')
        if mode=='malformed':return httpx.Response(200,json={'access_token':'secret'})
        if mode=='denied_identity':return httpx.Response(200,json={'sub':'one','email':'one@example.com','email_verified':False})
        return httpx.Response(400,json={'error':'invalid_grant','error_description':'sensitive refresh-token secret'})
    p=provider.GoogleMailboxProvider(settings,httpx.MockTransport(handler))
    with pytest.raises(provider.MailboxError) as caught:
        p.identity('secret') if mode=='denied_identity' else p.refresh('secret')
    assert 'secret' not in str(caught.value) and len(calls)==1


def test_missing_refresh_token_requires_consent_or_preserves_existing_refresh(setup):
    client,db,fake,(first,_),_=setup
    original=fake.exchange
    fake.exchange=lambda code,verifier:original(code,verifier).model_copy(update={'refresh_token':None})
    callback=begin(client,first)
    assert 'offline_consent_required' in client.get(callback,follow_redirects=False).headers['location']
    assert client.get('/api/mailboxes',headers=first).json()['items']==[]
    fake.exchange=original
    row=connect(client,first)
    fake.exchange=lambda code,verifier:original(code,verifier).model_copy(update={'refresh_token':None})
    callback=begin(client,first,['send'],row['id'])
    assert 'mailbox=connected' in client.get(callback,follow_redirects=False).headers['location']
    stored=db.get(MailboxConnection,uuid.UUID(row['id']))
    assert provider.unseal(fake.settings,service.context(stored),stored.credentials)['refresh_token']=='synthetic-refresh'


def test_secret_settings_are_not_serialized(settings):
    serialized=settings.model_dump_json()
    assert 'synthetic-secret' not in serialized and settings.JOBPILOT_MAILBOX_ENCRYPTION_KEY not in serialized
    assert 'synthetic-secret' not in repr(settings)
