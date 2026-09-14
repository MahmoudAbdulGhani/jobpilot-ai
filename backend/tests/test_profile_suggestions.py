from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.main import create_application
from app.models import CandidateProfile, User
from app.schemas.profile_suggestions import ProviderSuggestionOutput
from app.services.ai_provider import OpenAIResponsesProvider, ProviderFailure
from app.services import profile_suggestion_service
from tests.test_resume_extraction import pdf_bytes


@pytest.fixture()
def suggestion_client(db_session, tmp_path, monkeypatch):
    app = create_application()
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    settings = get_settings()
    monkeypatch.setattr(settings, "RESUME_STORAGE_DIR", str(tmp_path / "resumes"))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def suggestion_users(db_session):
    users = [User(email=f"suggest-{name}@test.local", password_hash=hash_password("password-123")) for name in ("one", "two")]
    db_session.add_all(users)
    db_session.commit()
    return users


def headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def confirmed_resume(client, user):
    uploaded = client.post("/api/resumes", headers=headers(user), files={"file": ("cv.pdf", pdf_bytes("Senior Engineer"), "application/pdf")}).json()
    resume_id = uploaded["id"]
    client.post(f"/api/resumes/{resume_id}/extract", headers=headers(user))
    client.post(f"/api/resumes/{resume_id}/extraction/confirm", headers=headers(user))
    return resume_id


def enable_fake(monkeypatch):
    settings = get_settings()
    for name, value in {
        "JOBPILOT_AI_ENABLED": True,
        "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": settings.POSTGRES_TEST_DB,
    }.items():
        monkeypatch.setattr(settings, name, value)


def test_ai_disabled_and_unconfirmed_are_rejected(suggestion_client, suggestion_users, monkeypatch):
    owner, _ = suggestion_users
    resume_id = confirmed_resume(suggestion_client, owner)
    response = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert response.status_code == 503
    enable_fake(monkeypatch)
    suggestion_client.patch(f"/api/resumes/{resume_id}/extraction", headers=headers(owner), json={"draft_text": "changed"})
    response = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert response.status_code == 409


def test_generate_does_not_mutate_profile_and_apply_is_selected_and_idempotent(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    owner, _ = suggestion_users
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    generated = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "ready"
    assert body["suggestions"][0]["evidence"][0]["quote"] == "Senior Engineer"
    assert suggestion_client.get("/api/profile", headers=headers(owner)).status_code == 404

    selection = body["suggestions"][0]
    selection["value"] = "Reviewed Senior Engineer"
    applied = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply",
        headers=headers(owner), json={"selections": [selection]},
    )
    assert applied.status_code == 200
    assert suggestion_client.get("/api/profile", headers=headers(owner)).json()["headline"] == "Reviewed Senior Engineer"
    repeated = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply",
        headers=headers(owner), json={"selections": [selection]},
    )
    assert repeated.status_code == 200
    selection["value"] = "Different"
    assert suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply",
        headers=headers(owner), json={"selections": [selection]},
    ).status_code == 409
    profile = db_session.query(CandidateProfile).filter_by(owner_id=owner.id).one()
    assert profile.ai_provenance["headline"]["source_available"] is True
    suggestion_client.delete(f"/api/resumes/{resume_id}", headers=headers(owner))
    db_session.refresh(profile)
    assert profile.headline == "Reviewed Senior Engineer"
    assert profile.ai_provenance["headline"]["source_available"] is False
    assert "evidence" not in profile.ai_provenance["headline"]


def test_ownership_source_conflict_and_discard(suggestion_client, suggestion_users, monkeypatch):
    owner, other = suggestion_users
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    body = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)).json()
    assert suggestion_client.get(f"/api/profile-suggestions/{body['id']}", headers=headers(other)).status_code == 404
    suggestion_client.patch(f"/api/resumes/{resume_id}/extraction", headers=headers(owner), json={"draft_text": "new confirmed source"})
    suggestion_client.post(f"/api/resumes/{resume_id}/extraction/confirm", headers=headers(owner))
    assert suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply", headers=headers(owner),
        json={"selections": body["suggestions"]},
    ).status_code == 409
    assert suggestion_client.delete(f"/api/profile-suggestions/{body['id']}", headers=headers(owner)).status_code == 204


def test_openai_adapter_uses_responses_structured_output_without_storage():
    captured = {}
    parsed = ProviderSuggestionOutput(suggestions=[])
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: captured.update(kwargs) or SimpleNamespace(status="completed", output_parsed=parsed)))
    provider = OpenAIResponsesProvider(api_key="test", model="model", timeout=3, max_output_tokens=100, client=client)
    assert provider.suggest("synthetic CV") == parsed
    assert captured["store"] is False
    assert captured["text_format"] is ProviderSuggestionOutput
    assert "synthetic CV" == captured["input"]


def test_openai_adapter_maps_incomplete_and_transport_errors():
    incomplete = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(status="incomplete", output_parsed=None)))
    with pytest.raises(ProviderFailure):
        OpenAIResponsesProvider(api_key="x", model="m", timeout=1, max_output_tokens=1, client=incomplete).suggest("cv")


def test_invalid_and_unsupported_evidence_is_removed():
    output = ProviderSuggestionOutput.model_validate({"suggestions": [
        {"id": "missing-quote", "field": "headline", "value": "Engineer", "evidence": [{"quote": "not present"}]},
        {"id": "long-skill", "field": "skills", "value": "x" * 101, "evidence": [{"quote": "Python"}]},
    ]})
    accepted, partial = profile_suggestion_service.validate_output(output, "Python")
    assert accepted == []
    assert partial is True


def test_stale_profile_blocks_apply(suggestion_client, suggestion_users, monkeypatch):
    owner, _ = suggestion_users
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    body = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)).json()
    suggestion_client.patch("/api/profile", headers=headers(owner), json={"headline": "Manual edit"})
    response = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply", headers=headers(owner),
        json={"selections": body["suggestions"]},
    )
    assert response.status_code == 409
    assert suggestion_client.get("/api/profile", headers=headers(owner)).json()["headline"] == "Manual edit"
