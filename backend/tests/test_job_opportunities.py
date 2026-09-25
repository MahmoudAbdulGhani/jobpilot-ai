"""Worldwide source contract checks. Every transport is mocked."""
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.services.discovery_provider import DiscoveryError, JobTechProvider
from app.services.discovery_sources import SOURCES, validate
from app.services.job_opportunities_provider import JobOpportunitiesProvider, parse_job, safe_link
from app.services.job_opportunities_catalog import JobOpportunitiesCatalog, now

ID = "12345678-1234-4234-8234-123456789abc"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("External provider call"))


def listing(**changes):
    return {"id": ID, "title": "Backend Engineer", "company": "Demo Global", "status": "live",
        "location": "New York, USA", "country": "US", "state": "NY", "city": "New York",
        "remote": "remote", "remote_inferred": True, "source": "greenhouse",
        "apply_url": "https://employer.example/jobs/123", "description": "Python required; Java preferred.",
        **changes}


def test_normalizes_distinct_workplace_eligibility_and_provenance():
    job = parse_job(listing())
    assert job.workplace_country == "US" and job.workplace_region == "NY" and job.workplace_city == "New York"
    assert job.applicant_region is None and job.remote_inferred is True
    assert job.upstream_source == "greenhouse" and job.apply_url == "https://employer.example/jobs/123"
    assert job.description == "Python required; Java preferred."


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://employer.example/job", "https://localhost/job",
    "https://127.0.0.1/job", "https://user:pass@employer.example/job", "https://employer.example:8443/job"])
def test_unsafe_apply_links_are_rejected(url):
    assert safe_link(url) is None
    with pytest.raises(DiscoveryError): parse_job(listing(apply_url=url))


@pytest.mark.parametrize("changes", [{"id":"not-an-id"},{"title":" "},{"description":"x"*50_001},
    {"remote":"outside"},{"remote_inferred":"false"},{"status":"closed"}])
def test_malformed_or_closed_rows_fail_safely(changes):
    with pytest.raises(DiscoveryError) as caught: parse_job(listing(**changes))
    assert caught.value.status == 502


def test_public_first_page_and_detail_use_fixed_endpoints():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [listing(description=None)]} if request.url.path == "/public/jobs" else {"data": listing()})
    source = JobOpportunitiesProvider(httpx.MockTransport(handler))
    found, total = source.search(q="backend", remote=True, sort="relevance", offset=0, country="US", region="NY", city="New York")
    assert total == 1 and found[0].description is None
    assert source.preview(ID).description == "Python required; Java preferred."
    assert calls[0].url.host == "api.jobopportunitiesapi.org"
    assert dict(calls[0].url.params) == {"limit":"50","q":"backend","country":"US","state":"NY","city":"New York","remote":"remote","remote_confirmed":"true"}
    assert str(calls[1].url) == "https://api.jobopportunitiesapi.org/public/jobs/" + ID
    assert all("authorization" not in request.headers for request in calls)


def test_one_listing_without_a_safe_application_link_does_not_hide_valid_results():
    def handler(request):
        return httpx.Response(200, json={"data": [listing(apply_url=None), listing()]})
    jobs, total = JobOpportunitiesProvider(httpx.MockTransport(handler)).search(
        q="", remote=False, sort="relevance", offset=0)
    assert total == 1 and len(jobs) == 1
    assert jobs[0].source_url == "https://employer.example/jobs/123"


@pytest.mark.parametrize("status,expected", [(429,429),(404,410),(500,503),(302,503)])
def test_safe_errors_and_no_redirect_or_retry(status, expected):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private response", headers={"Location":"http://localhost/secret"})
    with pytest.raises(DiscoveryError) as caught:
        JobOpportunitiesProvider(httpx.MockTransport(handler)).preview(ID)
    assert caught.value.status == expected and "private" not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("kwargs", [dict(source="jobicy",country="US"),dict(source="jobtech",eligibility="EMEA"),
    dict(source="jobopportunities",country="FR",region="NY"),dict(source="jobopportunities",offset=20),
    dict(source="jobtech",country="Sweden",city="Stockholm")])
def test_capability_validation_rejects_unsupported_filters(kwargs):
    name = kwargs.pop("source")
    with pytest.raises(DiscoveryError) as caught: validate(name, **kwargs)
    assert caught.value.status == 422


def test_registry_has_distinct_capabilities():
    assert "eligibility" in SOURCES["jobicy"]["filters"]
    assert "eligibility" not in SOURCES["jobopportunities"]["filters"]
    assert SOURCES["jobopportunities"]["pagination"] == "single_page"


def test_jobtech_taxonomy_ids_are_applied_to_geography():
    calls = []
    labels = {"country":"Sverige","region":"Stockholms län","municipality":"Stockholm"}
    def handler(request):
        calls.append(request)
        if request.url.host == "taxonomy.api.jobtechdev.se":
            kind = request.url.path.rsplit("/",1)[-1]
            return httpx.Response(200,json=[{"taxonomy/id":"tax_"+kind,"taxonomy/preferred-label":labels[kind]}])
        return httpx.Response(200,json={"hits":[],"total":{"value":0}})
    source = JobTechProvider(httpx.MockTransport(handler))
    assert source.search(q="python",remote=False,sort="relevance",offset=0,country="Sweden",region="Stockholms län",city="Stockholm") == ([],0)
    params = dict(calls[-1].url.params)
    assert params["country"] == "tax_country" and params["region"] == "tax_region" and params["municipality"] == "tax_municipality"


def test_shared_query_cache_and_durable_rate_claim_without_network():
    cache = SimpleNamespace(payload={}, next_attempt_at=now()-timedelta(seconds=1), refreshed_at=None)
    rate = SimpleNamespace(payload={"count":0}, next_attempt_at=now()-timedelta(seconds=1), refreshed_at=None)
    class FakeDB:
        def execute(self, _): pass
        def scalar(self, statement):
            sql = str(statement.compile(compile_kwargs={"literal_binds":True}))
            return rate if "joa-rate" in sql else cache
        def get(self, model, key, populate_existing=False): return cache
        def commit(self): pass
    class Stub:
        calls = 0
        def search(self, **filters):
            self.calls += 1
            return [parse_job(listing(description=None))], 1
    stub = Stub()
    catalog = JobOpportunitiesCatalog(FakeDB(), stub)
    filters = dict(q="python",remote=False,sort="relevance",offset=0,country="US",region="",city="")
    assert catalog.search(**filters)[1] == 1
    assert catalog.search(**filters)[1] == 1
    assert stub.calls == 1 and rate.payload["count"] == 1
    cache.next_attempt_at = now()-timedelta(seconds=1)
    rate.payload = {"count":35}
    with pytest.raises(DiscoveryError) as caught: catalog.search(**filters)
    assert caught.value.status == 429 and stub.calls == 1
