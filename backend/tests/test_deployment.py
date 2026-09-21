import uuid
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.main import create_application
from app.models import User, Resume
from app.services import resume_store, resume_service
from app.services.object_store import SupabaseStore, StorageUnavailable
from app.storage_inventory import inventory


def production(tmp_path, **changes):
    ca=tmp_path/'ca.pem';ca.write_text('synthetic-ca-placeholder')
    values=dict(ENVIRONMENT='production',SECRET_KEY='aB3!cD4@eF5#gH6$iJ7%kL8^mN9&oP0*',
        POSTGRES_HOST='db.example.com',POSTGRES_USER='synthetic',POSTGRES_PASSWORD='synthetic-db-password',AUTH_COOKIE_SECURE=True,
        JOBPILOT_APP_URL='https://app.example.com',CORS_ORIGINS=['https://app.example.com'],
        ALLOWED_HOSTS=['app.example.com','api.example.com'],POSTGRES_SSLMODE='verify-full',POSTGRES_SSLROOTCERT=str(ca),
        JOBPILOT_STORAGE='supabase',JOBPILOT_STORAGE_URL='https://synthetic.supabase.co',
        JOBPILOT_STORAGE_BUCKET='private-resumes',JOBPILOT_STORAGE_KEY='synthetic-storage-secret',JOBPILOT_DEBUG=False)
    values.update(changes)
    return Settings(_env_file=None,**values)


@pytest.mark.parametrize('change',[
    {'JOBPILOT_DEBUG':True},{'E2E_TEST_MODE':True},{'JOBPILOT_AI_TEST_PROVIDER':True},
    {'JOBPILOT_MAILBOX_TEST_PROVIDER':True},{'JOBPILOT_DISCOVERY_TEST_PROVIDER':True},{'JOBPILOT_VOICE_TEST_PROVIDER':True},
    {'AUTH_COOKIE_SECURE':False},{'JOBPILOT_APP_URL':'http://app.example.com'},
    {'CORS_ORIGINS':['*']},{'ALLOWED_HOSTS':['*']},{'JOBPILOT_PROXY_IPS':'*'},
    {'JOBPILOT_PROXY_IPS':'0.0.0.0/0'},{'POSTGRES_HOST':'localhost'},
    {'POSTGRES_SSLMODE':'require'},{'POSTGRES_PASSWORD':''},{'SECRET_KEY':'x'*40},
    {'JOBPILOT_STORAGE':'local'},{'JOBPILOT_STORAGE_KEY':''},{'JOBPILOT_STORAGE_BUCKET':'../bad'},
    {'JOBPILOT_ACCOUNT_MAIL_TRANSPORT':'test'},
    {'JOBPILOT_STORAGE_URL':'https://credential:secret@storage.example.com'},
])
def test_production_rejects_insecure_configuration(tmp_path,change):
    with pytest.raises(ValidationError) as error: production(tmp_path,**change)
    assert 'synthetic-storage-secret' not in str(error.value)
    assert 'synthetic-db-password' not in str(error.value)


def test_disabled_optional_integrations_and_tls(tmp_path):
    settings=production(tmp_path)
    assert not settings.JOBPILOT_AI_ENABLED
    assert settings.JOBPILOT_ACCOUNT_MAIL_TRANSPORT=='disabled'
    assert 'sslmode=verify-full' in settings.database_url
    assert 'synthetic-storage-secret' not in repr(settings)


def store(monkeypatch, handler):
    s=get_settings().model_copy(update={'JOBPILOT_STORAGE':'supabase','JOBPILOT_STORAGE_URL':'https://synthetic.supabase.co',
        'JOBPILOT_STORAGE_BUCKET':'private-resumes','JOBPILOT_STORAGE_KEY':'synthetic-secret'})
    provider=SupabaseStore(s,transport=httpx.MockTransport(handler))
    monkeypatch.setattr(resume_store,'object_store',lambda:provider)
    return provider


def test_object_bytes_private_download_owner_isolation_and_delete(monkeypatch,db_session):
    objects={};calls=[]
    def handler(request):
        calls.append((request.method,request.url.path))
        assert request.headers['authorization']=='Bearer synthetic-secret'
        if '/bucket/' in request.url.path: return httpx.Response(200,json={'public':False})
        key=request.url.path
        if request.method=='POST':
            assert request.headers['x-upsert']=='false'
            objects[key]=request.content;return httpx.Response(200,json={})
        if request.method=='DELETE': objects.pop(key,None);return httpx.Response(200,json={})
        return httpx.Response(200,content=objects[key]) if key in objects else httpx.Response(404)
    store(monkeypatch,handler)
    users=[User(email=f'store-{uuid.uuid4()}@example.com',password_hash=hash_password('synthetic-password')) for _ in range(2)]
    db_session.add_all(users);db_session.commit()
    data=b'%PDF-1.4\nunaltered\x00\xfforiginal\n%%EOF'
    row=resume_service.create_resume(db_session,owner_id=users[0].id,original_filename='cv.pdf',display_name='cv.pdf',file_extension='pdf',size_bytes=len(data),data=data)
    app=create_application();app.dependency_overrides[get_db]=lambda:db_session
    with TestClient(app) as client:
        before=len(calls)
        assert client.get(f'/api/resumes/{row.id}/download',headers={'Authorization':'Bearer '+create_access_token(users[1].id)}).status_code==404
        assert len(calls)==before
        assert client.delete(f'/api/resumes/{row.id}',headers={'Authorization':'Bearer '+create_access_token(users[1].id)}).status_code==404
        assert len(calls)==before
        response=client.get(f'/api/resumes/{row.id}/download',headers={'Authorization':'Bearer '+create_access_token(users[0].id)})
        assert response.content==data and response.status_code==200
        assert 'no-store' in response.headers['cache-control']
        assert 'synthetic-secret' not in str(response.headers)
    resume_service.delete_resume(db_session,resume=row)
    assert not objects


@pytest.mark.parametrize('response', [httpx.Response(200,json={'public':True}),httpx.Response(403,text='secret-provider-body'),httpx.Response(200,json={})])
def test_public_or_unknown_bucket_refused(monkeypatch,response):
    calls=[]
    provider=store(monkeypatch,lambda request:(calls.append(request.url.path) or response))
    with pytest.raises(StorageUnavailable) as error: provider.read(uuid.uuid4())
    assert len(calls)==1 and 'secret-provider-body' not in str(error.value)


def test_delete_failure_keeps_metadata(monkeypatch,db_session):
    def handler(request):
        if '/bucket/' in request.url.path:return httpx.Response(200,json={'public':False})
        raise httpx.ReadTimeout('credentials-and-body')
    store(monkeypatch,handler)
    user=User(email=f'delete-{uuid.uuid4()}@example.com',password_hash=hash_password('synthetic-password'))
    db_session.add(user);db_session.flush()
    row=Resume(owner_id=user.id,original_filename='cv.pdf',display_name='CV',file_extension='pdf',size_bytes=1)
    db_session.add(row);db_session.commit()
    with pytest.raises(StorageUnavailable): resume_service.delete_resume(db_session,resume=row)
    assert db_session.get(Resume,row.id) is not None


def test_inventory_is_read_only_and_never_calls_storage(monkeypatch,db_session,tmp_path):
    monkeypatch.setattr(resume_store,'object_store',lambda:pytest.fail('No provider call permitted'))
    user=User(email=f'inventory-{uuid.uuid4()}@example.com',password_hash=hash_password('synthetic-password'))
    db_session.add(user);db_session.flush()
    row=Resume(owner_id=user.id,original_filename='private-name.pdf',display_name='CV',file_extension='pdf',size_bytes=3)
    db_session.add(row);db_session.flush()
    path=tmp_path/str(row.id);path.write_bytes(b'abc')
    report=inventory(db_session,tmp_path)
    item=next(x for x in report['items'] if x['id']==str(row.id))
    assert item['status']=='ok' and report['provider_requests']==0
    assert 'private-name' not in str(report) and path.read_bytes()==b'abc'


def test_host_and_request_logging_boundaries(monkeypatch,caplog):
    app=create_application()
    @app.get('/crash')
    def crash():raise RuntimeError('private CV email password')
    with TestClient(app) as client:
        with caplog.at_level('INFO',logger='jobpilot.operations'):
            response=client.get('/crash?token=secret',headers={'X-Request-ID':'malicious-body','Authorization':'Bearer secret'})
        assert response.status_code==500
        assert len(response.headers['x-request-id'])==32
        assert 'private CV' not in response.text+caplog.text
        assert 'malicious-body' not in caplog.text and 'token=secret' not in caplog.text
        assert client.get('/api/health',headers={'Host':'attacker.example'}).status_code==400


def test_ready_schema_mismatch_and_database_error(monkeypatch):
    from app.api.routes import health
    class DB:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):pass
        def scalar(self,*args):return 'wrong-head'
    monkeypatch.setattr(health,'SessionLocal',DB)
    with TestClient(create_application()) as client:
        assert client.get('/api/ready').status_code==503
        assert client.get('/api/health').status_code==200


@pytest.mark.parametrize('status',[302,403,429,500])
def test_storage_failures_do_not_redirect_retry_or_expose_bodies(monkeypatch,status):
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        if '/bucket/' in request.url.path:return httpx.Response(200,json={'public':False})
        return httpx.Response(status,headers={'Location':'https://attacker.example'},text='credential-or-cv-body')
    provider=store(monkeypatch,handler)
    with pytest.raises(StorageUnavailable) as error:provider.read(uuid.uuid4())
    assert len(calls)==2 and 'credential' not in str(error.value)


def test_storage_diagnostic_logs_never_expose_secrets(monkeypatch, caplog):
    secret_key = 'super-secret-storage-key-abc123xyz'
    bucket_name = 'my-private-bucket'
    s = get_settings().model_copy(update={
        'JOBPILOT_STORAGE': 'supabase',
        'JOBPILOT_STORAGE_URL': 'https://project.supabase.co',
        'JOBPILOT_STORAGE_BUCKET': bucket_name,
        'JOBPILOT_STORAGE_KEY': secret_key,
    })

    def bucket_not_found(r):
        return httpx.Response(404, text='bucket not found')

    def auth_error(r):
        return httpx.Response(401, text='invalid apikey: ' + secret_key)

    def server_error(r):
        if '/bucket/' in r.url.path:
            return httpx.Response(200, json={'public': False})
        return httpx.Response(500, text='internal error with creds')

    def timeout_error(r):
        if '/bucket/' in r.url.path:
            return httpx.Response(200, json={'public': False})
        raise httpx.TimeoutException('connection to ' + secret_key + ' timed out')

    def public_bucket(r):
        return httpx.Response(200, json={'public': True})

    forbidden_body = r'{"message":" forbidden","hint":"check storage key ' + secret_key + '"}'
    def forbidden_on_write(r):
        if '/bucket/' in r.url.path:
            return httpx.Response(200, json={'public': False})
        return httpx.Response(403, text=forbidden_body)

    for handler, op_label in [
        (bucket_not_found, 'bucket_404'),
        (auth_error, 'bucket_auth_error'),
        (server_error, 'write_500'),
        (timeout_error, 'read_timeout'),
        (public_bucket, 'public_bucket'),
        (forbidden_on_write, 'write_403'),
    ]:
        provider = SupabaseStore(s, transport=httpx.MockTransport(handler))
        caplog.clear()
        with caplog.at_level('WARNING', logger='app.services.object_store'):
            with pytest.raises(StorageUnavailable):
                if op_label == 'write_500' or op_label == 'write_403':
                    provider.write(uuid.uuid4(), b'test-data')
                else:
                    provider.read(uuid.uuid4())
        log_text = caplog.text
        assert secret_key not in log_text, f'{op_label}: secret key leaked into logs'
        assert bucket_name not in log_text, f'{op_label}: bucket name leaked into logs'
        assert 'Bearer ' not in log_text, f'{op_label}: Bearer token leaked into logs'
        assert 'apikey' not in log_text.lower() or 'category' in log_text.lower(), (
            f'{op_label}: apikey header value leaked into logs'
        )
        assert 'storage_request' in log_text or 'storage_bucket_check' in log_text or 'storage_write' in log_text or 'storage_read' in log_text or 'storage_delete' in log_text, (
            f'{op_label}: expected diagnostic log line missing'
        )
        for line in log_text.splitlines():
            if 'storage_' in line:
                assert 'category=' in line, f'{op_label}: log line missing category field'


def test_production_startup_error_does_not_print_environment_secrets():
    import os, subprocess, sys
    env={**os.environ,'ENVIRONMENT':'production','SECRET_KEY':'startup-secret-marker',
         'POSTGRES_PASSWORD':'private-database-marker'}
    result=subprocess.run([sys.executable,'-m','app.production'],env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode!=0
    output=result.stdout+result.stderr
    assert 'Production configuration invalid' in output
    assert 'startup-secret-marker' not in output and 'private-database-marker' not in output


def test_release_is_one_explicit_locked_operation(monkeypatch):
    from app import release
    calls=[]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql): calls.append(str(sql))
    connection=Connection()
    monkeypatch.setattr(release.engine,'begin',lambda:connection)
    def upgrade(config,target):
        assert config.attributes['connection'] is connection and target=='head'
        calls.append('upgrade')
    monkeypatch.setattr(release.command,'upgrade',upgrade)
    release.main()
    assert len(calls)==3 and 'pg_advisory_xact_lock' in calls[1] and calls[-1]=='upgrade'
