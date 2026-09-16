from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.main import create_application
from app.models import CandidateProfile, User
from app.schemas.profile import CandidateProfileUpdate
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
              "BSc Computer Science at Example University. Fluent French.")
    output = ProviderSuggestionOutput.model_validate({"suggestions": [
        {"id": "exp-1", "field": "experience",
         "value": {"title": "Engineer", "organization": "Cedar Demo", "period": "2021-2024"},
         "evidence": [{"quote": "Engineer at Cedar Demo, 2021-2024"}]},
        {"id": "edu-1", "field": "education",
         "value": {"school": "Example University", "degree": "BSc", "field": "Computer Science"},
         "evidence": [{"quote": "BSc Computer Science at Example University"}]},
        {"id": "lang-1", "field": "languages",
         "value": {"name": "French", "proficiency": "professional"},
         "evidence": [{"quote": "Fluent French"}]},
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
    schema = ProviderSuggestionOutput.model_json_schema()
    defs = schema["$defs"]
    suggestions = schema["properties"]["suggestions"]
    assert suggestions["type"] == "array"
    variants = {ref["$ref"].split("/")[-1] for ref in suggestions["items"]["anyOf"]}
    assert variants == {
        "HeadlineSuggestion", "LocationSuggestion", "SkillsSuggestion",
        "ExperienceSuggestion", "EducationSuggestion", "LanguageSuggestion",
    }
    assert defs["ExperienceSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/ExperienceEntry"}
    assert defs["EducationSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/EducationEntry"}
    assert defs["LanguageSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/LanguageEntry"}
    assert defs["ExperienceEntry"]["required"] == ["job_title", "organization"]
    assert defs["HeadlineSuggestion"]["properties"]["value"]["type"] == "string"
    assert defs["HeadlineSuggestion"]["properties"]["value"]["maxLength"] == 200
    assert defs["SkillsSuggestion"]["properties"]["value"]["maxLength"] == 100
    assert defs["LocationSuggestion"]["properties"]["value"]["maxLength"] == 300
    # The wire schema drops only tautological keys and duplicated id/quote/value
    # min-bounds; the typed structure ("required", "$ref", enums, maxLength,
    # additionalProperties) stays so the provider still sees the contract.
    assert defs["HeadlineSuggestion"]["properties"]["id"] == {"type": "string"}
    for branch in ("HeadlineSuggestion", "ExperienceSuggestion"):
        assert defs[branch]["additionalProperties"] is False
        assert set(defs[branch]["required"]) == {"id", "field", "value", "evidence"}
        assert "minLength" not in defs[branch]["properties"]["id"]
        assert "maxLength" not in defs[branch]["properties"]["id"]
        assert "pattern" not in defs[branch]["properties"]["id"]
    assert "maxItems" not in schema["properties"]["suggestions"]
    assert "minLength" not in defs["HeadlineSuggestion"]["properties"]["value"]
    assert defs["Evidence"]["properties"]["quote"] == {"type": "string"}
    assert defs["HeadlineSuggestion"]["properties"]["field"] == {"type": "string", "const": "headline"}


def test_wire_compaction_never_weakens_local_parse():
    """The wire schema may omit id bounds, value minLength and quote length
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
    suggestion_client, suggestion_users, monkeypatch
):
    owner, _ = suggestion_users
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
