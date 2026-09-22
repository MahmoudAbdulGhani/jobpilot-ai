from types import SimpleNamespace
import uuid
from datetime import datetime, timezone

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.main import create_application
from app.models import AIUsage, CandidateProfile, ProfileSuggestionSet, UsageReservation, User
from app.schemas.profile import CandidateProfileUpdate
from app.schemas.profile_suggestions import (
    ALL_SUGGESTION_FIELDS, ProviderSuggestionOutput, ProviderWireSuggestionOutput,
    SuggestionSetResponse,
)
from app.services.ai_provider import OpenAIResponsesProvider, ProviderFailure, _profile_failure_field
from app.services import profile_suggestion_service
from consent_helpers import grant_consent
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


def confirmed_resume(client, user, text="Senior Engineer"):
    uploaded = client.post("/api/resumes", headers=headers(user), files={"file": ("cv.pdf", pdf_bytes(text), "application/pdf")}).json()
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


def test_ai_disabled_and_unconfirmed_are_rejected(suggestion_client, suggestion_users, db_session, monkeypatch):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
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
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    generated = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "ready"
    assert body["suggestions"][0]["evidence"][0]["quote"] == "Senior Engineer"
    assert suggestion_client.get("/api/profile", headers=headers(owner)).status_code == 404

    selection = body["suggestions"][0]
    selection["value"] = "Senior Engineer"
    applied = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply",
        headers=headers(owner), json={"selections": [selection]},
    )
    assert applied.status_code == 200
    assert suggestion_client.get("/api/profile", headers=headers(owner)).json()["headline"] == "Senior Engineer"
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
    assert profile.headline == "Senior Engineer"
    assert profile.ai_provenance["headline"]["source_available"] is False
    assert "evidence" not in profile.ai_provenance["headline"]


def test_ownership_source_conflict_and_discard(suggestion_client, suggestion_users, db_session, monkeypatch):
    owner, other = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    body = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)).json()
    assert suggestion_client.get(f"/api/profile-suggestions/{body['id']}", headers=headers(other)).status_code == 404
    suggestion_client.patch(f"/api/resumes/{resume_id}/extraction", headers=headers(owner), json={"draft_text": "new confirmed source"})
    suggestion_client.post(f"/api/resumes/{resume_id}/extraction/confirm", headers=headers(owner))
    assert suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply", headers=headers(owner),
        json={"selections": [item for item in body["suggestions"] if item.get("status") != "not_found"]},
    ).status_code == 409
    assert suggestion_client.delete(f"/api/profile-suggestions/{body['id']}", headers=headers(owner)).status_code == 204


def test_openai_adapter_uses_responses_structured_output_without_storage():
    captured = {}
    parsed = ProviderSuggestionOutput(suggestions=[], not_found=sorted(ALL_SUGGESTION_FIELDS))
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: captured.update(kwargs) or SimpleNamespace(status="completed", output_parsed=parsed.model_dump())))
    provider = OpenAIResponsesProvider(api_key="test", model="model", timeout=3, max_output_tokens=100, client=client)
    assert provider.suggest("synthetic CV") == parsed
    assert captured["store"] is False
    from app.schemas.profile_suggestions import ProviderWireSuggestionOutput
    assert captured["text_format"] is ProviderWireSuggestionOutput
    assert "synthetic CV" == captured["input"]
    assert captured["model"] == "model"
    assert captured["max_output_tokens"] == 100
    assert "reasoning" not in captured


def test_profile_provider_loads_openai_key_and_timeout(monkeypatch):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("openai.OpenAI", client)
    settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True,
        "JOBPILOT_AI_TEST_PROVIDER": False,
        "JOBPILOT_AI_PROVIDER": "openai",
        "JOBPILOT_AI_MODEL": "gpt-5-mini",
        "JOBPILOT_OPENAI_API_KEY": "synthetic-key",
        "JOBPILOT_AI_TIMEOUT_SECONDS": 17,
    })
    provider = profile_suggestion_service.provider_for(settings)

    assert provider.model == "gpt-5-mini"
    assert provider.timeout == 17
    assert captured == {"api_key": "synthetic-key", "timeout": 17, "max_retries": 0}


def _status_error(status, code):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, request=request)
    return openai.APIStatusError(
        "sensitive upstream detail", response=response, body={"code": code}
    )


@pytest.mark.parametrize(("upstream", "category"), [
    (_status_error(401, "invalid_api_key"), "authentication"),
    (_status_error(429, "insufficient_quota"), "billing"),
    (_status_error(429, "rate_limit_exceeded"), "rate_limit"),
    (_status_error(404, "model_not_found"), "model_unavailable"),
    (_status_error(400, "invalid_request_error"), "invalid_request"),
    (openai.APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")), "timeout"),
    (openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")), "provider_unavailable"),
    (RuntimeError("sensitive unknown failure"), "unknown"),
])
def test_profile_provider_exposes_only_safe_failure_category(upstream, category):
    def fail(**kwargs):
        raise upstream

    client = SimpleNamespace(responses=SimpleNamespace(parse=fail))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )

    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert str(caught.value) == category
    assert caught.value.category == category
    assert "sensitive" not in str(caught.value)


def test_openai_adapter_maps_incomplete_and_transport_errors():
    incomplete = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(status="incomplete", output_parsed=None)))
    with pytest.raises(ProviderFailure):
        OpenAIResponsesProvider(api_key="x", model="m", timeout=1, max_output_tokens=1, client=incomplete).suggest("cv")


def test_structured_contract_categories_are_allowlisted_safe_categories():
    """Every new diagnostic label must be in the safe set, or each one
    collapses back to the opaque 'unknown' bucket."""
    from app.services.ai_provider import SAFE_PROVIDER_FAILURE_CATEGORIES
    names = (
        "structured_output_invalid", "request_contract_invalid",
        "invalid_field_value", "invalid_evidence_reference", "unsupported_claim",
        "invalid_experience_shape", "invalid_education_shape", "invalid_salary_shape",
        "invalid_preference_value", "response_contract_invalid",
    )
    for name in names:
        assert name in SAFE_PROVIDER_FAILURE_CATEGORIES
        assert ProviderFailure(name).category == name


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
def test_profile_provider_noncompleted_status_maps_to_structured_output_invalid(status):
    client = SimpleNamespace(responses=SimpleNamespace(
        parse=lambda **kwargs: SimpleNamespace(status=status, output_parsed=None)))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert caught.value.category == "structured_output_invalid" == str(caught.value)


def test_profile_provider_null_parsed_output_maps_to_structured_output_invalid():
    client = SimpleNamespace(responses=SimpleNamespace(
        parse=lambda **kwargs: SimpleNamespace(status="completed", output_parsed=None)))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert caught.value.category == "structured_output_invalid" == str(caught.value)


def test_profile_provider_envelope_parse_failure_maps_to_structured_output_invalid():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    upstream = openai.APIResponseValidationError(response=httpx.Response(200, request=request), body=None)

    def fail(**kwargs):
        raise upstream

    client = SimpleNamespace(responses=SimpleNamespace(parse=fail))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert caught.value.category == "structured_output_invalid" == str(caught.value)


def test_profile_provider_local_contract_violation_maps_to_invalid_field_value():
    """A flat-wire-validated payload that still violates the local domain
    contract (a headline above the 200-char bound but inside the 300-char
    wire text bound) must fail as invalid_field_value, never as the opaque
    'unknown' category."""
    broken = {
        "suggestions": [{
            "id": "headline-1", "field": "headline",
            "value": {"text": "x" * 250},
            "evidence": [{"quote": "Synthetic evidence"}],
        }],
        "not_found": sorted(ALL_SUGGESTION_FIELDS - {"headline"}),
    }
    client = SimpleNamespace(responses=SimpleNamespace(
        parse=lambda **kwargs: SimpleNamespace(status="completed", output_parsed=broken)))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert caught.value.category == "invalid_field_value" == str(caught.value)
    assert caught.value.field == "headline"
    assert "private CV text" not in str(caught.value)


def _wire(parsed):
    return SimpleNamespace(status="completed", output_parsed=parsed)


def _run_seeded_provider(parsed, source="private CV text"):
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: _wire(parsed)))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest(source)
    assert isinstance(caught.value.category, str)
    return caught.value


def _seeded(present=None, suggestion=None, exception=None, *, raw=None):
    if raw is not None:
        return raw
    suggestion = suggestion or {
        "id": "h-1", "field": "headline",
        "value": {"text": "Synthetic headline"},
        "evidence": [{"quote": "Synthetic evidence"}],
    }
    payload = {
        "suggestions": [suggestion],
        "not_found": sorted(ALL_SUGGESTION_FIELDS - ({suggestion["field"]} if present is None else present)),
    }
    if exception:
        payload.update(exception)
    return payload


def _mutate(mutation_key):
    if mutation_key == "invalid_field_value":
        return _seeded(suggestion={
            "id": "h-1", "field": "headline",
            "value": {"text": "x" * 250},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "invalid_evidence_reference":
        return _seeded(suggestion={
            "id": "h-1", "field": "headline",
            "value": {"text": "Synthetic headline"},
            "evidence": [{"quote": "x" * 1001}]})
    if mutation_key == "unsupported_claim":
        return _seeded(suggestion={
            "id": "p-1", "field": "publications",
            "value": {"text": "Synthetic paper"},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "invalid_experience_shape":
        return _seeded(suggestion={
            "id": "e-1", "field": "experience",
            "value": {"experience": {"organization": "Cedar Inc."}},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "invalid_education_shape":
        return _seeded(suggestion={
            "id": "ed-1", "field": "education",
            "value": {"education": {"degree": "BSc"}},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "invalid_salary_shape":
        return _seeded(suggestion={
            "id": "s-1", "field": "salary_preference",
            "value": {"salary": {"currency": "USD", "min": 90000, "max": 50000}},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "invalid_preference_value":
        return _seeded(suggestion={
            "id": "r-1", "field": "remote_preference",
            "value": {"remote_preference": "onsite"},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "response_contract_invalid":
        return _seeded(suggestion={
            "id": "h-1", "field": "headline",
            "value": {"text": "Synthetic headline", "salary": {"currency": "USD"}},
            "evidence": [{"quote": "Synthetic evidence"}]})
    if mutation_key == "unknown":
        return [{
            "id": "h-1", "field": "headline",
            "value": {"text": "x"},
            "evidence": [{"quote": "q"}]}]
    raise AssertionError(mutation_key)


@pytest.mark.parametrize("mutation_key, category, field", [
    ("invalid_field_value", "invalid_field_value", "headline"),
    ("invalid_evidence_reference", "invalid_evidence_reference", None),
    ("unsupported_claim", "unsupported_claim", None),
    ("invalid_experience_shape", "invalid_experience_shape", None),
    ("invalid_education_shape", "invalid_education_shape", None),
    ("invalid_salary_shape", "invalid_salary_shape", None),
    ("invalid_preference_value", "invalid_preference_value", None),
    ("response_contract_invalid", "response_contract_invalid", None),
    ("unknown", "unknown", None),
])
def test_profile_provider_classifies_each_validation_failure_to_its_safe_category(mutation_key, category, field):
    """Each local wire/domain rejection resolves to its exact diagnostic label,
    and no provider input or exception text ever reaches the surface error."""
    parsed = _mutate(mutation_key)
    caught = _run_seeded_provider(parsed)
    assert caught.category == category == str(caught)
    assert caught.field == field
    assert "private CV text" not in str(caught)
    assert "Synthetic" not in str(caught)


def _wire_field_case(field, bucket):
    return {
        "suggestions": [{
            "id": f"{field}-1", "field": field, "value": bucket,
            "evidence": [{"quote": "Synthetic evidence"}],
        }],
        "not_found": sorted(ALL_SUGGESTION_FIELDS - {field}),
    }


@pytest.mark.parametrize("field, bucket", [
    ("headline", {"text": "x" * 301}),
    ("location", {"text": "x" * 301}),
    ("target_roles", {"text": "x" * 301}),
    ("skills", {"text": "x" * 301}),
    ("experience", {"experience": {"organization": "Cedar Inc."}}),
    ("education", {"education": {"degree": "BSc"}}),
    ("languages", {"language": {}}),
    ("remote_preference", {"remote_preference": "onsite"}),
    ("work_authorization", {"work_authorization": "onsite"}),
    ("salary_preference", {"salary": {"min": 100, "max": 50}}),
])
def test_profile_failure_field_is_identified_for_each_wire_field(field, bucket):
    """Every supported suggestion field falls out of the pydantic error
    location alone, with no value ever inspected or returned."""
    payload = _wire_field_case(field, bucket)
    with pytest.raises(ValidationError) as caught:
        ProviderWireSuggestionOutput.model_validate(payload)
    assert _profile_failure_field(caught.value, payload) == field
    assert _profile_failure_field(caught.value, payload) in {
        "headline", "location", "target_roles", "skills", "experience", "education",
        "languages", "remote_preference", "work_authorization", "salary_preference",
        "unknown",
    }


def test_profile_failure_field_domain_step_identifies_the_field_without_values():
    """The bare domain re-validation loc carries no index, so the field is
    recovered by re-validating each suggestion's own domain conversion."""
    payload = {
        "suggestions": [{
            "id": "h-1", "field": "headline",
            "value": {"text": "x" * 250}, "evidence": [{"quote": "q"}],
        }],
        "not_found": sorted(ALL_SUGGESTION_FIELDS - {"headline"}),
    }
    wire = ProviderWireSuggestionOutput.model_validate(payload)
    with pytest.raises(ValidationError) as caught:
        wire.to_domain()
    assert _profile_failure_field(caught.value, wire) == "headline"


def test_profile_failure_field_unknown_fallback_without_correlatable_location():
    """An envelope-level error with no suggestion index or items must degrade
    to 'unknown', never to a guessed field."""
    payload = {"partial": False}
    with pytest.raises(ValidationError) as caught:
        ProviderWireSuggestionOutput.model_validate(payload)
    assert _profile_failure_field(caught.value, payload) == "unknown"


@pytest.mark.parametrize("code", ["invalid_json_schema", "json_validate_failed", "schema_validation_failed"])
def test_profile_provider_schema_rejection_maps_to_request_contract_invalid(code):
    def fail(**kwargs):
        raise _status_error(400, code)

    client = SimpleNamespace(responses=SimpleNamespace(parse=fail))
    provider = OpenAIResponsesProvider(
        api_key="synthetic-key", model="gpt-5-mini", timeout=30,
        max_output_tokens=4000, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert caught.value.category == "request_contract_invalid" == str(caught.value)
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize("category", [
    "structured_output_invalid", "request_contract_invalid",
    "invalid_field_value", "invalid_evidence_reference", "unsupported_claim",
    "invalid_experience_shape", "invalid_education_shape", "invalid_salary_shape",
    "invalid_preference_value", "response_contract_invalid",
])
def test_new_profile_failure_categories_persist_only_safe_label_and_release_reservation(
    category, suggestion_client, suggestion_users, db_session, monkeypatch
):
    """A provider raising any diagnostic category must land in the persisted
    record as that exact safe label (never leaking details) and the failed
    reservation must be released."""
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)

    class Broken:
        name = "openai"
        model = "gpt-5-mini"

        def suggest(self, source):
            raise ProviderFailure(category)

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Broken())
    response = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["outcome_message"] == category
    record = db_session.query(ProfileSuggestionSet).filter_by(owner_id=owner.id).one()
    assert record.status == "failed"
    assert record.outcome_message == category
    usage = db_session.get(AIUsage, owner.id)
    reservation = db_session.query(UsageReservation).filter_by(owner_id=owner.id).one()
    assert usage.active_token is None and usage.active_until is None
    assert reservation.released_at is not None


def test_profile_failure_releases_reservation_and_persists_only_category(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)

    class Broken:
        name = "openai"
        model = "gpt-5-mini"

        def suggest(self, source):
            raise ProviderFailure("authentication")

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Broken())
    response = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["outcome_message"] == "authentication"
    record = db_session.query(ProfileSuggestionSet).filter_by(owner_id=owner.id).one()
    usage = db_session.get(AIUsage, owner.id)
    reservation = db_session.query(UsageReservation).filter_by(owner_id=owner.id).one()
    assert record.outcome_message == "authentication"
    assert usage.active_token is None and usage.active_until is None
    assert reservation.released_at is not None


def test_profile_failure_field_round_trips_through_post_latest_and_detail(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    """invalid_field_value carries a safe field label persisted and served by
    the generate, latest, and detail endpoints."""
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)

    class Broken:
        name = "openai"
        model = "gpt-5-mini"

        def suggest(self, source):
            raise ProviderFailure("invalid_field_value", field="experience")

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Broken())
    response = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["outcome_message"] == "invalid_field_value"
    assert body["failure_field"] == "experience"
    assert "experience" in {
        "headline", "location", "target_roles", "skills", "experience", "education",
        "languages", "remote_preference", "work_authorization", "salary_preference",
        "unknown",
    }

    record = db_session.query(ProfileSuggestionSet).filter_by(owner_id=owner.id).one()
    assert record.failure_field == "experience"

    latest = suggestion_client.get(
        f"/api/profile-suggestions/resumes/{resume_id}/latest", headers=headers(owner)
    ).json()
    assert latest["failure_field"] == "experience"
    detail = suggestion_client.get(
        f"/api/profile-suggestions/{record.id}", headers=headers(owner)
    ).json()
    assert detail["failure_field"] == "experience"


def test_profile_failure_field_never_exposes_unlisted_values(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    """A field identifier outside the closed set is dropped at the boundary and
    never persisted or returned."""
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)

    class Broken:
        name = "openai"
        model = "gpt-5-mini"

        def suggest(self, source):
            raise ProviderFailure("invalid_field_value", field="cv-text-or-secret")

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Broken())
    response = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["outcome_message"] == "invalid_field_value"
    assert body["failure_field"] is None
    record = db_session.query(ProfileSuggestionSet).filter_by(owner_id=owner.id).one()
    assert record.failure_field is None


def test_profile_failure_field_is_nullable_in_model_and_response_schema():
    """The persistence model and public response expose a nullable
    failure_field; older and successful rows simply carry null."""
    from app.models import ProfileSuggestionSet
    assert ProfileSuggestionSet.__table__.c.failure_field.nullable is True
    annotations = dict(SuggestionSetResponse.model_fields)
    assert "failure_field" in annotations
    assert annotations["failure_field"].is_required() is False
    assert SuggestionSetResponse(
        id=uuid.UUID(int=0), resume_id=uuid.UUID(int=1), source_hash="h",
        source_reviewed_at=datetime.now(timezone.utc), profile_revision="none",
        status="ready", suggestions=None, provider="openai", model="m",
        prompt_version="v3", outcome_message=None, applied_at=None, apply_result=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).model_dump().get("failure_field") is None
    assert SuggestionSetResponse(
        id=uuid.UUID(int=0), resume_id=uuid.UUID(int=1), source_hash="h",
        source_reviewed_at=datetime.now(timezone.utc), profile_revision="none",
        status="failed", suggestions=None, provider="openai", model="m",
        prompt_version="v3", outcome_message="invalid_field_value",
        failure_field="experience", applied_at=None, apply_result=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ).model_dump()["failure_field"] == "experience"


def test_invalid_and_unsupported_evidence_is_removed():
    output = ProviderSuggestionOutput.model_validate({"suggestions": [
        {"id": "missing-quote", "field": "headline", "value": "Engineer",
         "evidence": [{"quote": "not present"}]},
    ]})
    accepted, partial = profile_suggestion_service.validate_output(output, "Python")
    assert accepted == []
    assert partial is True


def test_plain_string_structured_values_fail_at_provider_boundary():
    """The demonstrated pilot failure (experience/education as plain strings)
    is now rejected by the provider contract itself, before application
    validation even runs."""
    with pytest.raises(ValidationError):
        ProviderSuggestionOutput.model_validate({"suggestions": [
            {"id": "experience-1", "field": "experience",
             "value": "Engineer at Cedar Demo, 2021-2024",
             "evidence": [{"quote": "Engineer at Cedar Demo, 2021-2024"}]},
        ]})
    with pytest.raises(ValidationError):
        ProviderSuggestionOutput.model_validate({"suggestions": [
            {"id": "education-1", "field": "education",
             "value": "BSc Computer Science, Example University, 2020",
             "evidence": [{"quote": "BSc Computer Science, Example University, 2020"}]},
        ]})
    with pytest.raises(ValidationError):
        ProviderSuggestionOutput.model_validate({"suggestions": [
            {"id": "long-skill", "field": "skills", "value": "x" * 101,
             "evidence": [{"quote": "Python"}]},
        ]})


def test_typed_structured_values_validate_with_source_evidence():
    source = ("Engineer at Cedar Demo, 2021-2024. "
              "BSc Computer Science at Example University. Fluent French (professional).")
    output = ProviderSuggestionOutput.model_validate({"suggestions": [
        {"id": "exp-1", "field": "experience",
         "value": {"title": "Engineer", "organization": "Cedar Demo", "period": "2021-2024"},
         "evidence": [{"quote": "Engineer at Cedar Demo, 2021-2024"}]},
        {"id": "edu-1", "field": "education",
         "value": {"school": "Example University", "degree": "BSc", "field": "Computer Science"},
         "evidence": [{"quote": "BSc Computer Science at Example University"}]},
        {"id": "lang-1", "field": "languages",
         "value": {"name": "French", "proficiency": "professional"},
         "evidence": [{"quote": "Fluent French (professional)"}]},
    ]})
    accepted, partial = profile_suggestion_service.validate_output(output, source)
    assert [item["field"] for item in accepted] == ["experience", "education", "languages"]
    assert partial is False
    assert accepted[0]["value"]["title"] == "Engineer"
    assert accepted[0]["value"]["organization"] == "Cedar Demo"
    CandidateProfileUpdate.model_validate(
        {item["field"]: [item["value"]] for item in accepted})


def test_language_requires_explicit_proficiency_evidence():
    output = ProviderSuggestionOutput.model_validate({"suggestions": [{
        "id": "language-1", "field": "languages",
        "value": {"name": "Arabic", "proficiency": "professional"},
        "evidence": [{"quote": "Languages: Arabic"}],
    }]})
    assert profile_suggestion_service.validate_output(output, "Languages: Arabic") == ([], True)


@pytest.mark.parametrize("value", [
    "Tripoli, Lebanon | +961 76 364 340 | Mahmoud.Abdulghani@outlook.com",
    "Tripoli, Lebanon | Mahmoud.Abdulghani@outlook.com",
    "Tripoli, Lebanon | +961 76 364 340",
    "Beirut 076364340",
])
def test_location_suggestion_rejects_phone_and_email_contact_details(value):
    source = f"Location: {value}"
    output = ProviderSuggestionOutput.model_validate({"suggestions": [{
        "id": "location-1", "field": "location", "value": value,
        "evidence": [{"quote": source}],
    }]})
    assert profile_suggestion_service.validate_output(output, source) == ([], True)


def test_plain_city_country_location_is_still_accepted():
    source = "Location: Tripoli, Lebanon"
    output = ProviderSuggestionOutput.model_validate({"suggestions": [{
        "id": "location-1", "field": "location", "value": "Tripoli, Lebanon",
        "evidence": [{"quote": source}],
    }]})
    accepted, partial = profile_suggestion_service.validate_output(output, source)
    assert partial is False
    assert accepted == [{
        "id": "location-1", "field": "location", "value": "Tripoli, Lebanon",
        "evidence": [{"quote": source}],
    }]


def test_contact_block_location_is_never_offered_as_profile_location(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    source = "\n".join([
        "Full-Stack Software Engineer",
        "Tripoli, Lebanon | +961 76 364 340 | Mahmoud.Abdulghani@outlook.com",
    ])
    resume_id = confirmed_resume(suggestion_client, owner, source)
    output = ProviderSuggestionOutput.model_validate({
        "suggestions": [{
            "id": "location-1", "field": "location",
            "value": "Tripoli, Lebanon | +961 76 364 340 | Mahmoud.Abdulghani@outlook.com",
            "evidence": [{"quote": "Tripoli, Lebanon | +961 76 364 340 | Mahmoud.Abdulghani@outlook.com"}],
        }],
        "not_found": sorted(ALL_SUGGESTION_FIELDS - {"location"}),
    })

    class SyntheticProvider:
        name = "openai"
        model = "gpt-5-mini"

        def suggest(self, text):
            assert all(line in text for line in source.splitlines())
            return output

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: SyntheticProvider())
    generated = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "ready"
    assert body["outcome_message"] == "Some unsupported suggestions were removed."
    body_fields = {item["field"] for item in body["suggestions"]}
    assert "location" not in body_fields
    assert body_fields == ALL_SUGGESTION_FIELDS - {"location"}


def test_valid_experience_object_parses_and_applies_to_profile():
    """Minimal mocked reproduction: a valid experience suggestion parses and
    the value round-trips into CandidateProfileUpdate (the downstream apply
    target). See test_profile_wire_schema.py for the missing-title, wrong
    discriminator and plain-string reproductions of the live failure."""
    output = ProviderSuggestionOutput.model_validate(
        {"suggestions": [{
            "id": "exp-1", "field": "experience",
            "value": {"title": "Engineer", "organization": "Cedar Demo"},
            "evidence": [{"quote": "Engineer at Cedar Demo"}]}]})
    assert output.suggestions[0].value.title == "Engineer"
    CandidateProfileUpdate.model_validate(
        {"experience": [output.suggestions[0].value.model_dump()]})


def test_suggestion_schema_constrains_per_field_values():
    """The JSON schema sent to the provider must not have the value: Any
    loophole, and must be compatible with strict structured outputs: one flat
    suggestion with a strictly-required nullable value bucket per field, each
    typed to the shape it will be validated against downstream (no suggestion
    union, and anyOf used only for nullability)."""
    from app.schemas.profile_suggestions import ProviderWireSuggestionOutput

    schema = ProviderWireSuggestionOutput.model_json_schema()
    defs = schema["$defs"]
    suggestions = schema["properties"]["suggestions"]
    assert suggestions["type"] == "array"
    # The suggestion-level union is gone; the flat contract keeps each of the
    # ten field enums and the typed value buckets instead of anyOf branches.
    assert suggestions["items"] == {"$ref": "#/$defs/ProviderWireSuggestion"}
    suggestion = defs["ProviderWireSuggestion"]
    assert set(suggestion["required"]) == {"id", "field", "evidence", "value"}
    assert suggestion["additionalProperties"] is False
    assert suggestion["properties"]["value"] == {"$ref": "#/$defs/ProviderWireValue"}
    assert set(suggestion["properties"]["field"]["enum"]) == set(ALL_SUGGESTION_FIELDS)
    assert set(defs["ProviderExperienceEntry"]["required"]) == {
        "job_title", "organization", "period", "notes"}
    assert defs["ProviderExperienceEntry"]["properties"]["job_title"] == {
        "type": "string", "minLength": 1, "maxLength": 200}
    value = defs["ProviderWireValue"]
    assert set(value["required"]) == set(value["properties"])
    assert value["additionalProperties"] is False
    assert value["properties"]["experience"] == {
        "anyOf": [{"$ref": "#/$defs/ProviderExperienceEntry"}, {"type": "null"}]}
    assert value["properties"]["education"] == {
        "anyOf": [{"$ref": "#/$defs/EducationEntry"}, {"type": "null"}]}
    assert value["properties"]["language"] == {
        "anyOf": [{"$ref": "#/$defs/LanguageEntry"}, {"type": "null"}]}
    assert value["properties"]["salary"] == {
        "anyOf": [{"$ref": "#/$defs/SalaryPreference"}, {"type": "null"}]}
    text = value["properties"]["text"]
    assert {"type": "string", "maxLength": 300} in text["anyOf"]
    assert {"type": "null"} in text["anyOf"]
    assert {item["type"] for item in value["properties"]["remote_preference"]["anyOf"]} == {
        "string", "null"}
    # The flat schema drops only tautological keys and duplicated value/id
    # guidance; the typed structure (required, $ref, enums, maxLength,
    # additionalProperties, nullable anyOf) stays strict on the wire.
    id_spec = defs["ProviderWireSuggestion"]["properties"]["id"]
    assert id_spec == {"type": "string"}
    assert "anyOf" not in suggestions["items"]
    assert "maxItems" not in schema["properties"]["suggestions"]
    assert defs["Evidence"]["properties"]["quote"] == {"type": "string", "minLength": 1, "maxLength": 1000}
    for name in ("ProviderWireSuggestion", "ProviderWireValue", "ProviderExperienceEntry"):
        assert defs[name]["additionalProperties"] is False
        assert set(defs[name]["required"]) == set(defs[name]["properties"])


def test_explicit_cv_fields_generate_apply_and_keep_absent_languages_empty(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    source = "\n".join([
        "Full-Stack Software Engineer",
        "Location: Tripoli Lebanon",
        "Target role: Full-Stack Software Engineer",
        "Skills: Python TypeScript",
        "Software Engineer at Cedar Labs 2022-2025",
        "BSc Computer Science at Lebanese University 2022",
        "Remote preference: remote",
        "Work authorization: citizen",
        "Salary preference: USD 70000 to 90000",
    ])
    resume_id = confirmed_resume(suggestion_client, owner, source)
    output = ProviderSuggestionOutput.model_validate({
        "suggestions": [
            {"id": "headline-1", "field": "headline", "value": "Full-Stack Software Engineer", "evidence": [{"quote": "Full-Stack Software Engineer"}]},
            {"id": "location-1", "field": "location", "value": "Tripoli Lebanon", "evidence": [{"quote": "Location: Tripoli Lebanon"}]},
            {"id": "role-1", "field": "target_roles", "value": "Full-Stack Software Engineer", "evidence": [{"quote": "Target role: Full-Stack Software Engineer"}]},
            {"id": "skill-1", "field": "skills", "value": "Python", "evidence": [{"quote": "Skills: Python TypeScript"}]},
            {"id": "skill-2", "field": "skills", "value": "TypeScript", "evidence": [{"quote": "Skills: Python TypeScript"}]},
            {"id": "experience-1", "field": "experience", "value": {"title": "Software Engineer", "organization": "Cedar Labs", "period": "2022-2025"}, "evidence": [{"quote": "Software Engineer at Cedar Labs 2022-2025"}]},
            {"id": "education-1", "field": "education", "value": {"school": "Lebanese University", "degree": "BSc", "field": "Computer Science", "period": "2022"}, "evidence": [{"quote": "BSc Computer Science at Lebanese University 2022"}]},
            {"id": "remote-1", "field": "remote_preference", "value": "remote", "evidence": [{"quote": "Remote preference: remote"}]},
            {"id": "authorization-1", "field": "work_authorization", "value": "citizen", "evidence": [{"quote": "Work authorization: citizen"}]},
            {"id": "salary-1", "field": "salary_preference", "value": {"currency": "USD", "min": 70000, "max": 90000}, "evidence": [{"quote": "Salary preference: USD 70000 to 90000"}]},
        ],
        "not_found": ["languages"],
    })

    class SyntheticProvider:
        name = "openai"
        model = "gpt-5-mini"

        def suggest(self, text):
            assert all(line in text for line in source.splitlines())
            return output

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: SyntheticProvider())
    generated = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "ready"
    assert {item["field"] for item in body["suggestions"] if item.get("status") != "not_found"} == ALL_SUGGESTION_FIELDS - {"languages"}
    assert [item["field"] for item in body["suggestions"] if item.get("status") == "not_found"] == ["languages"]

    selections = [item for item in body["suggestions"] if item.get("status") != "not_found"]
    applied = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply",
        headers=headers(owner), json={"selections": selections},
    )
    assert applied.status_code == 200
    profile = suggestion_client.get("/api/profile", headers=headers(owner)).json()
    assert profile["headline"] == "Full-Stack Software Engineer"
    assert profile["location"] == "Tripoli Lebanon"
    assert profile["target_roles"] == ["Full-Stack Software Engineer"]
    assert profile["skills"] == ["Python", "TypeScript"]
    assert profile["experience"] == [{"title": "Software Engineer", "organization": "Cedar Labs", "period": "2022-2025", "notes": None}]
    assert profile["education"] == [{"school": "Lebanese University", "degree": "BSc", "field": "Computer Science", "period": "2022"}]
    assert profile["remote_preference"] == "remote"
    assert profile["work_authorization"] == "citizen"
    assert profile["salary_preference"] == {"currency": "USD", "min": 70000, "max": 90000}
    assert profile["languages"] is None


def test_wire_compaction_never_weakens_local_parse():
    """The wire schema may omit id bounds and value minLength
    guidance, but the production parse enforces the same constraints locally."""
    quote_ok = [{"id": "exp-1", "field": "experience",
                 "value": {"title": "Engineer", "organization": "Cedar Demo", "period": "2021-2024"},
                 "evidence": [{"quote": "Engineer at Cedar Demo, 2021-2024"}]}]
    valid = {"suggestions": quote_ok}
    ProviderSuggestionOutput.model_validate(valid)
    def invalid(**suggestion):
        return ProviderSuggestionOutput.model_validate(
            {"suggestions": [dict(quote_ok[0], **suggestion)]})
    with pytest.raises(ValidationError):
        invalid(id="has a space")
    with pytest.raises(ValidationError):
        invalid(id="x" * 65)
    with pytest.raises(ValidationError):
        invalid(id="x", value={"title": "Engineer", "organization": ""})
    with pytest.raises(ValidationError):
        invalid(id="x", evidence=[{"quote": ""}])
    with pytest.raises(ValidationError):
        invalid(id="x", evidence=[{"quote": "e" * 1001}])
    # A skills/id headline value that is an empty string is rejected locally
    # even though the wire schema no longer advertises minLength.
    with pytest.raises(ValidationError):
        ProviderSuggestionOutput.model_validate({"suggestions": [
            {"id": "headline-1", "field": "headline", "value": "",
             "evidence": [{"quote": "Backend engineer"}]}]})


def test_apply_rejects_out_of_contract_and_unsecured_values_without_profile_change(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    body = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)).json()

    # A fabricated experience selection with a plain-string value is rejected
    # at the API contract boundary before any profile mutation.
    forged = {"id": "experience-forged", "field": "experience",
              "value": "Engineer at Cedar Demo, 2021-2024",
              "evidence": [{"quote": "Engineer at Cedar Demo, 2021-2024"}]}
    response = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply", headers=headers(owner),
        json={"selections": [forged]},
    )
    assert response.status_code == 422
    assert suggestion_client.get("/api/profile", headers=headers(owner)).status_code == 404

    # Parses correctly but fabricates the supporting quote: rejected by the
    # strict evidence validator inside apply(), leaving the profile untouched.
    selection = dict(body["suggestions"][0])
    selection["evidence"] = [{"quote": "not in the confirmed CV"}]
    response = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply", headers=headers(owner),
        json={"selections": [selection]},
    )
    assert response.status_code == 422
    assert suggestion_client.get("/api/profile", headers=headers(owner)).status_code == 404


def test_stale_profile_blocks_apply(suggestion_client, suggestion_users, db_session, monkeypatch):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume_id = confirmed_resume(suggestion_client, owner)
    body = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner)).json()
    suggestion_client.patch("/api/profile", headers=headers(owner), json={"headline": "Manual edit"})
    response = suggestion_client.post(
        f"/api/profile-suggestions/{body['id']}/apply", headers=headers(owner),
        json={"selections": [item for item in body["suggestions"] if item.get("status") != "not_found"]},
    )
    assert response.status_code == 409
    assert suggestion_client.get("/api/profile", headers=headers(owner)).json()["headline"] == "Manual edit"


def test_profile_suggestions_without_consent_never_calls_provider(suggestion_client, suggestion_users, db_session, monkeypatch):
    from sqlalchemy import func, select
    from app.models import ProfileSuggestionSet
    owner, _ = suggestion_users
    enable_fake(monkeypatch)
    def forbidden(*a): pytest.fail("Suggestions provider must not be called without consent")
    monkeypatch.setattr(profile_suggestion_service, "provider_for", forbidden)
    resume_id = confirmed_resume(suggestion_client, owner)
    response = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert response.status_code == 403
    assert db_session.scalar(select(func.count()).select_from(ProfileSuggestionSet).where(ProfileSuggestionSet.owner_id == owner.id)) == 0


def test_profile_suggestions_consent_revoked_between_dispatches(suggestion_client, suggestion_users, db_session, monkeypatch):
    owner, _ = suggestion_users
    enable_fake(monkeypatch)
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    resume_id = confirmed_resume(suggestion_client, owner)
    first = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert first.status_code == 200
    grant_consent(db_session, owner.id, "ai_profile_suggestions", allowed=False)  # Revoked before the next dispatch.
    second = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert second.status_code == 403


def test_profile_consent_revoked_after_reservation_cancels_and_allows_retry(
    suggestion_client, suggestion_users, db_session, monkeypatch
):
    from unittest.mock import Mock
    from sqlalchemy import select
    from app.models import AIUsage, ProfileSuggestionSet, UsageReservation
    from app.services import ai_usage

    owner, _ = suggestion_users
    enable_fake(monkeypatch)
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    resume_id = confirmed_resume(suggestion_client, owner)
    original_reserve = ai_usage.reserve
    original_provider_for = profile_suggestion_service.provider_for
    provider = Mock()
    provider.name, provider.model = "must-not-run", "must-not-run"

    def revoke_after_reservation(*args, **kwargs):
        token = original_reserve(*args, **kwargs)
        grant_consent(db_session, owner.id, "ai_profile_suggestions", allowed=False)
        return token

    monkeypatch.setattr(ai_usage, "reserve", revoke_after_reservation)
    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda _: provider)
    denied = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert denied.status_code == 403
    provider.suggest.assert_not_called()

    record = db_session.scalar(select(ProfileSuggestionSet).where(
        ProfileSuggestionSet.owner_id == owner.id))
    assert record.status == "failed" and "cancelled" in record.outcome_message
    usage = db_session.get(AIUsage, owner.id)
    reservation = db_session.get(UsageReservation, usage.active_token) if usage.active_token else None
    assert usage.active_token is None and usage.active_until is None
    assert reservation is None
    released = db_session.scalar(select(UsageReservation).where(
        UsageReservation.owner_id == owner.id))
    assert released.released_at is not None

    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    monkeypatch.setattr(ai_usage, "reserve", original_reserve)
    monkeypatch.setattr(profile_suggestion_service, "provider_for", original_provider_for)
    retried = suggestion_client.post(
        f"/api/profile-suggestions/resumes/{resume_id}", headers=headers(owner))
    assert retried.status_code == 200 and retried.json()["status"] == "ready"
