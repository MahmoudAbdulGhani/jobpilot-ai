"""Mocked public provider and reviewed imports. Live HTTP is forbidden."""
import uuid
from datetime import timedelta
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import SavedJob, User
from app.models.discovery_cache import DiscoveryCache
from app.services import discovery_service
from app.services.discovery_provider import DiscoveryError, provider_for
from app.services.jobicy_provider import JobicyProvider, parse_job, CATALOG_LIMIT, MAX_RESPONSE_BYTES
from app.services.discovery_catalog import JobicyCatalog, now
from test_discovery import discovery_client, owners


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',lambda *a,**k:pytest.fail('No live HTTP'))


def listing(**changes):
    raw={'id':123,'url':'https://jobicy.com/jobs/123-backend-engineer','jobTitle':'Backend Engineer',
        'companyName':'Example &amp; Co','jobGeo':'EMEA','pubDate':'2026-09-17T08:00:00+00:00',
        'jobDescription':'<p>Build Python APIs.</p><script>secretScript()</script><p>Confirm eligible countries.</p>'}
    return {**raw,**changes}


def test_plain_text_eligibility_and_missing_values():
    job=parse_job(listing())
    assert job.description=='Build Python APIs.\nConfirm eligible countries.'
    assert job.company=='Example & Co' and job.remote_arrangement=='remote'
    assert job.applicant_region=='EMEA' and job.location is None
    assert job.salary is None and job.deadline is None
    missing=parse_job(listing(jobGeo=None,jobDescription=None))
    assert missing.applicant_region is None and missing.remote_arrangement=='remote'
    assert parse_job(listing(jobGeo='Anywhere')).applicant_region=='Anywhere'
    salary=parse_job(listing(salaryMin=40000,salaryMax=50000))
    assert 'Currency not supplied' in salary.salary and 'period not supplied' in salary.salary


@pytest.mark.parametrize('changes',[{'id':True},{'id':-1},{'jobTitle':'x'*201},{'jobDescription':'x'*100001},
    {'jobGeo':['Europe']},{'url':'http://localhost/secret'}, {'url':'https://jobicy.com.evil/jobs/123-role'},
    {'url':'https://jobicy.com/jobs/999-other'}, {'url':'https://jobicy.com/jobs/123-role?url=http://localhost'},
    {'salaryMin':True},{'salaryMin':100,'salaryMax':1},{'salaryMin':'1000'},{'pubDate':'invalid'}])
def test_malformed_listings_fail_safely(changes):
    with pytest.raises(DiscoveryError) as error:parse_job(listing(**changes))
    assert error.value.status==502


@pytest.mark.parametrize('status,expected',[(429,429),(503,503),(401,503),(302,503),(404,410),(410,410)])
def test_error_mapping_no_retry_no_redirect(status,expected):
    calls=[]
    def handler(request):
        calls.append(request);return httpx.Response(status,text='private raw body',headers={'Location':'http://localhost/'})
    provider=JobicyProvider(httpx.MockTransport(handler))
    with pytest.raises(DiscoveryError) as error:provider.catalog()
    assert error.value.status==expected and 'private' not in str(error.value) and len(calls)==1


def test_fixed_endpoint_and_documented_head():
    calls=[]
    def handler(request):
        calls.append(request);return httpx.Response(200,json={'jobs':[listing()]})
    provider=JobicyProvider(httpx.MockTransport(handler))
    jobs=provider.catalog();provider.check(jobs[0])
    assert str(calls[0].url)==f'https://jobicy.com/api/v2/remote-jobs?count={CATALOG_LIMIT}'
    assert calls[1].method=='HEAD' and str(calls[1].url)==listing()['url']
    assert 'authorization' not in calls[0].headers
    with pytest.raises(DiscoveryError):provider.check(jobs[0].model_copy(update={'source_url':'http://localhost/secret'}))
    assert len(calls)==2


@pytest.mark.parametrize('mode',['oversize','bad_json','wrong_shape','duplicates','timeout'])
def test_bounded_invalid_catalog(mode):
    def handler(request):
        if mode=='timeout':raise httpx.ReadTimeout('secret')
        if mode=='oversize':return httpx.Response(200,content=b'x'*(MAX_RESPONSE_BYTES+1))
        if mode=='bad_json':return httpx.Response(200,text='not json')
        return httpx.Response(200,json={'jobs':[listing(),listing()]} if mode=='duplicates' else {'jobs':{}})
    with pytest.raises(DiscoveryError):JobicyProvider(httpx.MockTransport(handler)).catalog()


class Stub:
    def __init__(self):self.calls=0;self.checks=0;self.failure=None
    def catalog(self):
        self.calls+=1
        if self.failure:raise DiscoveryError(self.failure,'Safe failure')
        return [parse_job(listing(id=i,url=f'https://jobicy.com/jobs/{i}-role',jobGeo='EMEA' if i%2 else None)) for i in range(1,31)]
    def check(self,job):
        self.checks+=1
        if self.failure:raise DiscoveryError(self.failure,'Safe failure')


def test_shared_cache_filters_pagination_and_expired_preview(db_session):
    stub=Stub();first=JobicyCatalog(db_session,stub);second=JobicyCatalog(db_session,stub)
    jobs,total=first.search(q='python',remote=True,sort='relevance',offset=0,location='EMEA')
    assert total==15 and all(j.applicant_region=='EMEA' for j in jobs)
    assert second.search(q='',remote=False,sort='relevance',offset=20)[1]==30
    assert len(second.search(q='',remote=False,sort='relevance',offset=20)[0])==10
    assert second.search(q='',remote=True,sort='relevance',offset=0,location='Lebanon')==([],0)
    assert stub.calls==1
    first.preview('1');second.preview('1');assert stub.checks==1
    stub.failure=410
    with pytest.raises(DiscoveryError) as error:first.preview('2')
    assert error.value.status==410
    with pytest.raises(DiscoveryError):second.preview('2')
    assert stub.checks==2
    assert first.search(q='',remote=False,sort='relevance',offset=0)[1]==29
    with pytest.raises(DiscoveryError):first.preview('http://localhost/')
    assert stub.calls==1 and stub.checks==2


def test_cache_failure_and_interrupted_attempt_are_not_retried(db_session):
    stub=Stub();stub.failure=429;catalog=JobicyCatalog(db_session,stub)
    for _ in range(2):
        with pytest.raises(DiscoveryError) as error:catalog.load()
        assert error.value.status==429
    assert stub.calls==1
    row=db_session.get(DiscoveryCache,'jobicy');row.next_attempt_at=now()-timedelta(seconds=1);db_session.commit()
    stub.failure=None;assert catalog.load()['jobs'];assert stub.calls==2
    row=db_session.get(DiscoveryCache,'jobicy');row.refreshed_at=None;row.payload={};db_session.commit()
    with pytest.raises(DiscoveryError):catalog.load()
    assert stub.calls==2


def test_preview_check_budget(db_session):
    stub=Stub();catalog=JobicyCatalog(db_session,stub)
    for i in range(1,21):catalog.preview(str(i))
    with pytest.raises(DiscoveryError) as error:catalog.preview('21')
    assert error.value.status==429 and stub.checks==20 and stub.calls==1


def test_cross_source_suggestions_owner_isolation_and_no_merging(db_session):
    owner=User(email=f'jobicy-{uuid.uuid4()}@example.com',password_hash='unused')
    other=User(email=f'jobicy-{uuid.uuid4()}@example.com',password_hash='unused')
    db_session.add_all([owner,other]);db_session.flush()
    first=SavedJob(owner_id=owner.id,title='Backend Engineer',company='Example & Co',source_provider='jobtech',source_external_id='123',notes='My edits')
    foreign=SavedJob(owner_id=other.id,title=first.title,company=first.company,source_provider='jobtech',source_external_id='123')
    db_session.add_all([first,foreign]);db_session.commit()
    settings=get_settings();source=parse_job(listing())
    preview=discovery_service.prepare_preview(db_session,owner.id,source,settings)
    assert preview.job.existing_job_id is None and preview.job.possible_duplicate_ids==[first.id]
    with pytest.raises(DiscoveryError):discovery_service.import_preview(db_session,other.id,preview.preview_token,settings)
    imported,duplicate=discovery_service.import_preview(db_session,owner.id,preview.preview_token,settings)
    assert not duplicate and imported.id!=first.id and imported.source_provider=='jobicy'
    imported.title='My title';imported.notes='Keep this';db_session.commit()
    again,duplicate=discovery_service.import_preview(db_session,owner.id,preview.preview_token,settings)
    assert duplicate and again.id==imported.id and again.notes=='Keep this' and again.title=='My title'
    assert first.notes=='My edits'
    assert discovery_service.with_duplicates(db_session,other.id,[source])[0].existing_job_id is None


def test_guarded_provider_selection_and_location_validation():
    settings=get_settings().model_copy(update={'JOBPILOT_DISCOVERY_ENABLED':True,'JOBPILOT_DISCOVERY_TEST_PROVIDER':True,'E2E_TEST_MODE':False})
    with pytest.raises(DiscoveryError):provider_for(settings,'jobicy')
    settings=settings.model_copy(update={'E2E_TEST_MODE':True,'POSTGRES_DB':settings.POSTGRES_TEST_DB})
    assert provider_for(settings,'jobicy').preview('123456').test_data


def test_source_and_location_input_validation(discovery_client,owners):
    from app.api.routes.discovery import provider as dependency
    discovery_client.app.dependency_overrides.pop(dependency)
    headers=owners[0]
    for query in ['source=unknown','location='+'x'*101,'offset=1981']:
        assert discovery_client.get('/api/discovery?'+query,headers=headers).status_code==422


def test_concurrent_cache_refresh_claim_dispatches_once(test_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import delete
    from sqlalchemy.orm import Session
    entered, finish = Event(), Event()
    class Slow(Stub):
        def catalog(self):
            entered.set();assert finish.wait(10)
            return super().catalog()
    provider=Slow()
    with Session(test_engine) as db:
        if db.get(DiscoveryCache,'jobicy'):
            pytest.skip('Existing public test cache preserved; concurrency mutation not authorized')
    def load():
        with Session(test_engine) as db:return JobicyCatalog(db,provider).load()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(load);assert entered.wait(5)
            with Session(test_engine) as db:
                with pytest.raises(DiscoveryError) as error:JobicyCatalog(db,provider).load()
                assert error.value.status==503
            finish.set();assert len(future.result(timeout=5)['jobs'])==30
        assert provider.calls==1
    finally:
        finish.set()
        with Session(test_engine) as db:
            row=db.get(DiscoveryCache,'jobicy')
            # Remove only the synthetic catalog this test created, never existing data.
            if row and row.payload.get('jobs')==[j.model_dump(mode='json') for j in Stub().catalog()]:
                db.execute(delete(DiscoveryCache).where(DiscoveryCache.source=='jobicy',DiscoveryCache.refreshed_at==row.refreshed_at));db.commit()
