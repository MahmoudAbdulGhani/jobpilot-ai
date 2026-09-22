from types import SimpleNamespace

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
from app.schemas.profile_suggestions import ProviderSuggestionOutput
from app.services.ai_provider import OpenAIResponsesProvider, ProviderFailure
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
        json={"selections": body["suggestions"]},
    ).status_code == 409
    assert suggestion_client.delete(f"/api/profile-suggestions/{body['id']}", headers=headers(owner)).status_code == 204


def test_openai_adapter_uses_responses_structured_output_without_storage():
    captured = {}
    parsed = ProviderSuggestionOutput(suggestions=[])
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
    loophole; each field's value is typed to the shape it will be validated
    against downstream."""
    from app.schemas.profile_suggestions import ProviderWireSuggestionOutput

    schema = ProviderWireSuggestionOutput.model_json_schema()
    defs = schema["$defs"]
    suggestions = schema["properties"]["suggestions"]
    assert suggestions["type"] == "array"
    variants = {ref["$ref"].split("/")[-1] for ref in suggestions["items"]["anyOf"]}
    assert variants == {
        "HeadlineSuggestion", "LocationSuggestion", "SkillsSuggestion",
        "ProviderExperienceSuggestion", "EducationSuggestion", "LanguageSuggestion",
    }
    assert defs["ProviderExperienceSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/ProviderExperienceEntry"}
    assert defs["EducationSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/EducationEntry"}
    assert defs["LanguageSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/LanguageEntry"}
    assert defs["ProviderExperienceEntry"]["required"] == ["job_title", "organization"]
    assert defs["HeadlineSuggestion"]["properties"]["value"]["type"] == "string"
    assert defs["HeadlineSuggestion"]["properties"]["value"]["maxLength"] == 200
    assert defs["SkillsSuggestion"]["properties"]["value"]["maxLength"] == 100
    assert defs["LocationSuggestion"]["properties"]["value"]["maxLength"] == 300
    # The wire schema drops only tautological keys and duplicated id/value
    # min-bounds; the typed structure ("required", "$ref", enums, maxLength,
    # additionalProperties) stays so the provider still sees the contract.
    assert defs["HeadlineSuggestion"]["properties"]["id"] == {"type": "string"}
    for branch in ("HeadlineSuggestion", "ProviderExperienceSuggestion"):
        assert defs[branch]["additionalProperties"] is False
        assert set(defs[branch]["required"]) == {"id", "field", "value", "evidence"}
        assert "minLength" not in defs[branch]["properties"]["id"]
        assert "maxLength" not in defs[branch]["properties"]["id"]
        assert "pattern" not in defs[branch]["properties"]["id"]
    assert "maxItems" not in schema["properties"]["suggestions"]
    assert "minLength" not in defs["HeadlineSuggestion"]["properties"]["value"]
    assert defs["Evidence"]["properties"]["quote"] == {"type": "string", "minLength": 1, "maxLength": 1000}
    assert defs["HeadlineSuggestion"]["properties"]["field"] == {"type": "string", "const": "headline"}


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
        json={"selections": body["suggestions"]},
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
