"""Pipe into the built container with --network none; synthetic values only."""
import os
import uuid
from pathlib import Path

assert os.getuid() == 10001
assert not Path('/app/.env').exists()
assert not Path('/app/backend/app/tools').exists()
Path('/tmp/jobpilot-smoke-ca.pem').write_text('synthetic certificate placeholder')
os.environ.update({
    'ENVIRONMENT':'production','SECRET_KEY':'aB3!cD4@eF5#gH6$iJ7%kL8^mN9&oP0*',
    'POSTGRES_HOST':'db.example.com','POSTGRES_USER':'synthetic','POSTGRES_PASSWORD':'synthetic',
    'POSTGRES_SSLMODE':'verify-full','POSTGRES_SSLROOTCERT':'/tmp/jobpilot-smoke-ca.pem',
    'AUTH_COOKIE_SECURE':'true','JOBPILOT_APP_URL':'https://app.example.com',
    'CORS_ORIGINS':'https://app.example.com','ALLOWED_HOSTS':'app.example.com',
    'JOBPILOT_STORAGE':'supabase','JOBPILOT_STORAGE_URL':'https://synthetic.supabase.co',
    'JOBPILOT_STORAGE_BUCKET':'private-cvs','JOBPILOT_STORAGE_KEY':'synthetic-storage-key',
})
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings
from app.services.object_store import SupabaseStore
import httpx

with TestClient(app,base_url='https://app.example.com') as client:
    assert client.get('/api/health').status_code==200
    assert client.get('/api/docs').status_code==404
    assert client.get('/api/health',headers={'Host':'attacker.example'}).status_code==400
    assert client.get('/api/account/options').json()=={'registration':'invite-only'}

objects={}
def respond(request):
    if '/bucket/' in request.url.path:return httpx.Response(200,json={'public':False})
    key=request.url.path
    if request.method=='POST':objects[key]=request.content;return httpx.Response(200)
    if request.method=='DELETE':objects.pop(key,None);return httpx.Response(200)
    return httpx.Response(200,content=objects[key])
store=SupabaseStore(get_settings(),transport=httpx.MockTransport(respond))
identifier=uuid.uuid4();original=b'%PDF synthetic\x00\xff bytes'
store.write(identifier,original)
assert store.read(identifier)==original
store.delete(identifier)
assert not objects
print('Container smoke passed: non-root, no local secrets/tools, production guards, liveness, private mocked byte round-trip; network disabled')
