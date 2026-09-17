"""Mocked JobTech parsing and connected import tests; no provider network calls."""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import SavedJob, User
from app.services import discovery_provider as provider
from app.api.routes.discovery import provider as provider_dependency


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *a, **k: pytest.fail("Live HTTP forbidden"))


def ad(**overrides):
    value = {"id": "12345", "headline": "Backend Engineer", "employer": {"name": "Demo AB"},
        "description": {"text": "Build Python APIs. <script>alert(1)</script>", "text_formatted": "<b>Do not render</b>"},
        "workplace_address": {"municipality": "Stockholm", "region": "Stockholm", "country": "Sweden"},
        "publication_date": "2026-09-17T09:00:00", "application_deadline": "2026-10-01T23:59:59",
        "webpage_url": "javascript:alert(1)"}
    value.update(overrides)
    return value


def test_documented_search_and_plain_text_parser():
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"hits": [ad()], "total": {"value": 1}})
    source = provider.JobTechProvider(httpx.MockTransport(handler))
    jobs, total = source.search(q="Python", remote=True, sort="pubdate-desc", offset=20)
    request = captured[0]
    assert str(request.url).startswith(provider.BASE_URL + "/search?")
    assert dict(request.url.params) == {"q": "Python", "remote": "true", "sort": "pubdate-desc", "offset": "20", "limit": "20", "resdet": "full"}
    assert total == 1 and jobs[0].external_id == "12345"
    assert jobs[0].location == "Stockholm, Sweden"
    assert jobs[0].salary is None and jobs[0].workplace_model is None
    assert jobs[0].source_url == "https://arbetsformedlingen.se/platsbanken/annonser/12345"
    assert jobs[0].description == ad()["description"]["text"]
    assert jobs[0].published_at == ad()["publication_date"]


@pytest.mark.parametrize("overrides", [{"headline": " "}, {"employer": {}}, {"headline": "x"*201},
    {"description": {"text": "x"*50_001}}, {"publication_date": "bad-date"}, {"id": "../../etc"},
    {"salary_description": 100}, {"workplace_address": ["invalid"]}])
def test_invalid_source_fields_are_rejected(overrides):
    with pytest.raises(provider.DiscoveryError) as error:
        provider.parse_job(ad(**overrides))
    assert error.value.status == 502


def test_missing_information_is_not_inferred():
    job = provider.parse_job(ad(description={"text_formatted": "<b>HTML only</b>"}, workplace_address=None))
    assert job.description is None and job.location is None
    assert job.salary is None and job.workplace_model is None


@pytest.mark.parametrize("status,expected", [(429,429),(500,503),(401,503),(302,503),(404,410)])
def test_provider_failures_are_safe_and_not_retried(status, expected):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="secret unrestricted provider body", headers={"Location": "http://localhost/secret"})
    source = provider.JobTechProvider(httpx.MockTransport(handler))
    with pytest.raises(provider.DiscoveryError) as caught:
        source.preview("12345")
    assert caught.value.status == expected and "secret" not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["invalid_json", "too_large", "timeout", "wrong_id", "removed"])
def test_bounded_response_and_preview(mode):
    def handler(request):
        if mode == "timeout": raise httpx.ReadTimeout("private details")
        if mode == "invalid_json": return httpx.Response(200, text="not json")
        if mode == "too_large": return httpx.Response(200, content=b"x"*(provider.MAX_RESPONSE_BYTES+1))
        return httpx.Response(200, json=ad(id="different") if mode == "wrong_id" else ad(removed=True))
    with pytest.raises(provider.DiscoveryError):
        provider.JobTechProvider(httpx.MockTransport(handler)).preview("12345")


def test_no_arbitrary_urls_or_test_provider_in_production():
    with pytest.raises(provider.DiscoveryError): provider.JobTechProvider().preview("https://localhost/secret")
    settings = get_settings().model_copy(update={"JOBPILOT_DISCOVERY_ENABLED": True, "JOBPILOT_DISCOVERY_TEST_PROVIDER": True, "E2E_TEST_MODE": False})
    with pytest.raises(provider.DiscoveryError): provider.provider_for(settings)


@pytest.fixture()
def discovery_client(client, db_session):
    def db(): yield db_session
    class MockSource:
        def search(self, **kwargs): return [provider.parse_job(ad())], 1
        def preview(self, external_id): return provider.parse_job(ad(id=external_id))
    client.app.dependency_overrides[get_db] = db
    client.app.dependency_overrides[provider_dependency] = MockSource
    yield client
    client.app.dependency_overrides.clear()


@pytest.fixture()
def owners(db_session):
    users = [User(email=f"discovery-{uuid.uuid4()}@jobpilot-test.com", password_hash="unused") for _ in range(2)]
    db_session.add_all(users); db_session.commit()
    return [{"Authorization": f"Bearer {create_access_token(u.id)}"} for u in users]


def test_review_import_owner_isolation_and_user_edits(discovery_client, owners, db_session):
    client, (first, second) = discovery_client, owners
    found = client.get("/api/discovery?q=Python", headers=first)
    assert found.status_code == 200 and found.json()["items"][0]["existing_job_id"] is None
    preview = client.get("/api/discovery/12345/preview", headers=first)
    assert preview.headers["cache-control"] == "no-store"
    token = preview.json()["preview_token"]
    assert client.get("/api/jobs", headers=first).json()["total"] == 0
    assert client.post("/api/discovery/import", headers=first, json={"preview_token":token}).status_code == 422
    assert client.post("/api/discovery/import", headers=second, json={"preview_token":token,"confirm":True}).status_code == 422
    created = client.post("/api/discovery/import", headers=first, json={"preview_token":token,"confirm":True})
    assert created.status_code == 201
    saved = created.json()["job"]
    assert saved["description"] == ad()["description"]["text"]
    assert saved["source_provider"] == "jobtech" and saved["source_external_id"] == "12345"
    assert saved["source_snapshot"]["published_at"] == ad()["publication_date"]
    path = f"/api/jobs/{saved['id']}"
    assert client.get(path, headers=second).status_code == 404
    assert client.patch(path, headers=first, json={"source_external_id":"other"}).status_code == 422
    assert client.patch(path, headers=first, json={"title":"My edited title","notes":"Keep this","is_archived":True}).status_code == 200
    again = client.post("/api/discovery/import", headers=first, json={"preview_token":token,"confirm":True})
    assert again.status_code == 200 and again.json()["already_saved"]
    assert again.json()["job"]["title"] == "My edited title" and again.json()["job"]["notes"] == "Keep this"
    assert again.json()["job"]["source_snapshot"]["title"] == "Backend Engineer"
    assert client.get("/api/discovery", headers=first).json()["items"][0]["existing_job_id"] == saved["id"]
    assert client.get("/api/discovery", headers=second).json()["items"][0]["existing_job_id"] is None
    second_token = client.get("/api/discovery/12345/preview", headers=second).json()["preview_token"]
    other = client.post("/api/discovery/import", headers=second, json={"preview_token":second_token,"confirm":True})
    assert other.status_code == 201 and other.json()["job"]["id"] != saved["id"]
    row = db_session.get(SavedJob, uuid.UUID(saved["id"]))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(SavedJob(owner_id=row.owner_id, title="Race", company="Race", source_provider="jobtech", source_external_id="12345")); db_session.flush()


def test_tampered_expired_and_access_tokens_rejected(discovery_client, owners):
    client, headers = discovery_client, owners[0]
    token = client.get("/api/discovery/12345/preview", headers=headers).json()["preview_token"]
    payload = jwt.decode(token, options={"verify_signature":False})
    payload["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(payload, get_settings().SECRET_KEY, algorithm="HS256")
    for invalid in (token + "bad", expired, headers["Authorization"].split()[1]):
        assert client.post("/api/discovery/import", headers=headers, json={"preview_token":invalid,"confirm":True}).status_code == 422


def test_query_validation_and_auth(discovery_client, owners):
    assert discovery_client.get("/api/discovery").status_code == 401
    for query in ("q="+"x"*201, "offset=2001", "sort=arbitrary", "remote=maybe"):
        assert discovery_client.get("/api/discovery?"+query, headers=owners[0]).status_code == 422


def test_additive_provenance_schema(test_engine):
    inspector = inspect(test_engine)
    columns = {c["name"]: c for c in inspector.get_columns("saved_jobs")}
    for field in ("source_provider", "source_external_id", "source_snapshot", "imported_at"):
        assert columns[field]["nullable"]
    index = next(i for i in inspector.get_indexes("saved_jobs") if i["name"] == "uq_saved_jobs_owner_source_external")
    assert index["unique"] and index["column_names"] == ["owner_id", "source_provider", "source_external_id"]


@pytest.mark.parametrize("status", [429, 503, 502, 410])
def test_safe_provider_errors_reach_api(discovery_client, owners, status):
    class FailingSource:
        def search(self, **kwargs): raise provider.DiscoveryError(status, "Safe provider explanation")
        def preview(self, external_id): raise provider.DiscoveryError(status, "Safe provider explanation")
    discovery_client.app.dependency_overrides[provider_dependency] = FailingSource
    for path in ("/api/discovery", "/api/discovery/12345/preview"):
        response = discovery_client.get(path, headers=owners[0])
        assert response.status_code == status and response.json() == {"detail":"Safe provider explanation"}
