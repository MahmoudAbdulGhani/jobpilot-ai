"""Offline regressions for the provider-only job_title compatibility workaround."""
import json
import socket

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.evaluation.validation_diagnostics import validation_diagnostics
from app.schemas.profile import CandidateProfileUpdate, CandidateProfileResponse
from app.schemas.profile_suggestions import ProviderSuggestionOutput, ProviderWireSuggestionOutput, _compact_wire_schema
from app.services.ai_provider import GroqResponsesProvider


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No network permitted")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def suggestion(field, value):
    return {"id": "synthetic", "field": field, "value": value,
            "evidence": [{"quote": "Synthetic evidence"}]}


def test_serialized_sdk_requires_job_title_and_maps_to_domain_title():
    captured = []

    def transport(request):
        captured.append(json.loads(request.content)["text"]["format"])
        return httpx.Response(200, json={
            "id": "offline", "object": "response", "created_at": 0,
            "model": "synthetic", "status": "completed",
            "output": [{"id": "msg", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "annotations": [], "text": json.dumps({"suggestions": [suggestion("experience", {
                            "job_title": "Engineer", "organization": "Synthetic",
                            "period": None, "notes": None})], "partial": False, "message": None})}]}],
        })

    with OpenAI(api_key="synthetic", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        output = GroqResponsesProvider(api_key="unused", model="synthetic", timeout=3,
                              max_output_tokens=1500, client=client).suggest("Synthetic evidence")
    assert output.suggestions[0].value.title == "Engineer"
    assert "job_title" not in output.model_dump()["suggestions"][0]["value"]
    assert len(captured) == 1
    assert captured[0]["strict"] is True
    local = ProviderSuggestionOutput.model_json_schema()
    compact = ProviderWireSuggestionOutput.model_json_schema()
    wire = captured[0]["schema"]
    local_entry = local["$defs"]["ExperienceEntry"]
    assert "title" in local_entry["required"]
    assert "job_title" not in local_entry["properties"]
    for schema in (compact, wire):
        entry = schema["$defs"]["ProviderExperienceEntry"]
        assert "job_title" in entry["required"]
        assert "organization" in entry["required"]
        assert "title" not in entry["properties"]
        assert entry["properties"]["job_title"] == {
            "type": "string", "minLength": 1, "maxLength": 200}
        assert entry["additionalProperties"] is False
        variants = {"HeadlineSuggestion": "headline", "LocationSuggestion": "location",
                    "SkillsSuggestion": "skills", "ProviderExperienceSuggestion": "experience",
                    "EducationSuggestion": "education", "LanguageSuggestion": "languages"}
        assert schema["$defs"]["ProviderExperienceSuggestion"]["properties"]["value"] == {
            "$ref": "#/$defs/ProviderExperienceEntry"}
        assert {item["$ref"] for item in schema["properties"]["suggestions"]["items"]["anyOf"]} == {
            f"#/$defs/{variant}" for variant in variants}
        for variant, literal in variants.items():
            branch = schema["$defs"][variant]
            assert set(branch["required"]) == {"id", "field", "value", "evidence"}
            assert branch["properties"]["field"]["const"] == literal
    assert set(wire["$defs"]["ProviderExperienceEntry"]["required"]) == {
        "job_title", "organization", "period", "notes"}


def test_compaction_preserves_names_that_match_metadata_keywords():
    schema = {"title": "Metadata", "type": "object", "properties": {
        name: {"title": "Metadata", "description": "Metadata", "default": "x", "type": "string"}
        for name in ("title", "description", "default")}, "required": ["title"]}
    compact = _compact_wire_schema(schema)
    assert "title" not in compact
    assert compact["properties"] == {name: {"type": "string"} for name in ("title", "description", "default")}
    assert compact["required"] == ["title"]
    assert "title" in schema  # Original schema remains untouched.


def test_missing_experience_title_reproduces_all_17_retained_errors():
    payload = {"suggestions": [suggestion("headline", "Synthetic") for _ in range(3)] + [
        suggestion("experience", {"organization": "Synthetic", "period": None, "notes": None})]}
    with pytest.raises(ValidationError) as caught:
        ProviderSuggestionOutput.model_validate_json(json.dumps(payload))
    diagnostic = validation_diagnostics(caught.value)["validation"]
    actual = {(e["type"], tuple(e["location"][2:])) for e in diagnostic["errors"]}
    # Complete retained error signature, without any original input values.
    expected = {
        ("missing", ("ExperienceSuggestion", "value", "title")),
        ("extra_forbidden", ("EducationSuggestion", "value", "organization")),
        ("extra_forbidden", ("EducationSuggestion", "value", "notes")),
        ("missing", ("EducationSuggestion", "value", "school")),
        ("missing", ("LanguageSuggestion", "value", "name")),
        ("missing", ("LanguageSuggestion", "value", "proficiency")),
    }
    for branch in ("HeadlineSuggestion", "LocationSuggestion", "SkillsSuggestion"):
        expected.add(("string_type", (branch, "value")))
    for branch in ("HeadlineSuggestion", "LocationSuggestion", "SkillsSuggestion", "EducationSuggestion", "LanguageSuggestion"):
        expected.add(("literal_error", (branch, "field")))
    for field in ("organization", "period", "notes"):
        expected.add(("extra_forbidden", ("LanguageSuggestion", "value", field)))
    assert actual == expected
    assert len(diagnostic["errors"]) == 17 and not diagnostic["errors_truncated"]
    assert all(e["location"][:2] == ["suggestions", 3] for e in diagnostic["errors"])


def test_missing_title_can_also_be_an_inapplicable_union_branch():
    # Invalid education generates an experience-title error too, but the
    # accompanying field literal error identifies that branch as inapplicable.
    with pytest.raises(ValidationError) as caught:
        ProviderSuggestionOutput.model_validate({"suggestions": [suggestion("education", {})]})
    errors = caught.value.errors(include_input=False, include_context=False, include_url=False)
    assert any(e["loc"] == ("suggestions", 0, "ExperienceSuggestion", "value", "title") for e in errors)
    assert any(e["type"] == "literal_error" and e["loc"] == (
        "suggestions", 0, "ExperienceSuggestion", "field") for e in errors)
    # Valid education needs no title at all.
    parsed = ProviderSuggestionOutput.model_validate({"suggestions": [suggestion("education", {"school": "Synthetic"})]})
    assert parsed.suggestions[0].field == "education"


@pytest.mark.parametrize("title", [None, "", "x" * 201])
def test_local_experience_title_validation_is_not_relaxed(title):
    value = {"organization": "Synthetic"}
    if title is not None:
        value["title"] = title
    with pytest.raises(ValidationError):
        ProviderSuggestionOutput.model_validate({"suggestions": [suggestion("experience", value)]})


def test_wire_job_title_parses_and_round_trips_to_domain_title():
    payload = {"suggestions": [{
        "id": "exp-1", "field": "experience",
        "value": {"job_title": "Engineer", "organization": "Cedar Demo",
                  "period": None, "notes": None},
        "evidence": [{"quote": "Engineer at Cedar Demo"}]}]}
    parsed = ProviderWireSuggestionOutput.model_validate(payload).to_domain()
    value = parsed.suggestions[0].value
    assert value.title == "Engineer"
    # Serialization and downstream apply keep the domain ``title`` shape.
    dumped = parsed.suggestions[0].model_dump(mode="json")
    assert dumped["value"] == {
        "title": "Engineer", "organization": "Cedar Demo",
        "period": None, "notes": None}
    CandidateProfileUpdate.model_validate({"experience": [value]})
    CandidateProfileUpdate.model_validate({"experience": [dumped["value"]]})


def test_client_selections_still_accept_the_domain_title_key():
    payload = {"suggestions": [{
        "id": "exp-1", "field": "experience",
        "value": {"title": "Engineer", "organization": "Cedar Demo"},
        "evidence": [{"quote": "Engineer at Cedar Demo"}]}]}
    parsed = ProviderSuggestionOutput.model_validate(payload)
    assert parsed.suggestions[0].value.title == "Engineer"


@pytest.mark.parametrize("model", [CandidateProfileUpdate, CandidateProfileResponse])
@pytest.mark.parametrize("entry,valid", [
    ({"title": "Engineer", "organization": "Synthetic"}, True),
    ({"title": "x" * 200, "organization": "x" * 200,
      "period": "x" * 100, "notes": "x" * 2000}, True),
    ({"job_title": "Engineer", "organization": "Synthetic"}, False),
    ({"title": "Engineer", "job_title": "Engineer", "organization": "Synthetic"}, False),
    ({"organization": "Synthetic"}, False),
    ({"title": "Engineer"}, False),
    ({"title": "", "organization": "Synthetic"}, False),
    ({"title": None, "organization": "Synthetic"}, False),
    ({"title": "x" * 201, "organization": "Synthetic"}, False),
    ({"title": "Engineer", "organization": ""}, False),
    ({"title": "Engineer", "organization": "x" * 201}, False),
    ({"title": "Engineer", "organization": "Synthetic", "period": "x" * 101}, False),
    ({"title": "Engineer", "organization": "Synthetic", "notes": "x" * 2001}, False),
])
def test_public_profile_experience_contract_before_ed05a0f(model, entry, valid):
    payload = {"experience": [entry]}
    if model is CandidateProfileResponse:
        payload.update({name: None for name in (
            "headline", "target_roles", "location", "remote_preference", "work_authorization",
            "skills", "education", "languages", "salary_preference")})
        payload.update(id="00000000-0000-0000-0000-000000000001",
                       owner_id="00000000-0000-0000-0000-000000000002",
                       created_at="2026-09-17T00:00:00Z", updated_at="2026-09-17T00:00:00Z")
    if valid:
        dumped = model.model_validate(payload).model_dump(mode="json")
        assert dumped["experience"][0]["title"] == entry["title"]
        assert "job_title" not in dumped["experience"][0]
    else:
        with pytest.raises(ValidationError):
            model.model_validate(payload)
    schema = model.model_json_schema()["$defs"]["ExperienceEntry"]
    assert schema["required"] == ["title", "organization"]
    assert "job_title" not in schema["properties"]


@pytest.mark.parametrize("changes", [
    {"job_title": None}, {"job_title": ""}, {"job_title": "x" * 201},
    {"organization": ""}, {"organization": "x" * 201},
    {"period": "x" * 101}, {"notes": "x" * 2001}, {"title": "Engineer"},
])
def test_provider_entry_preserves_bounds(changes):
    entry = {"job_title": "Engineer", "organization": "Synthetic", **changes}
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate({"suggestions": [suggestion("experience", entry)]})


@pytest.mark.parametrize("missing", ["job_title", "organization"])
def test_provider_entry_requires_fields(missing):
    entry = {"job_title": "Engineer", "organization": "Synthetic"}
    del entry[missing]
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate({"suggestions": [suggestion("experience", entry)]})


@pytest.mark.parametrize("evidence", [[], [{"quote": ""}], [{"quote": "x" * 1001}]])
def test_provider_evidence_constraints(evidence):
    item = suggestion("experience", {"job_title": "Engineer", "organization": "Synthetic"})
    item["evidence"] = evidence
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate({"suggestions": [item]})


def test_mapped_experience_preserves_evidence_validation():
    from app.services.profile_suggestion_service import validate_output
    item = suggestion("experience", {"job_title": "Engineer", "organization": "Synthetic"})
    output = ProviderWireSuggestionOutput.model_validate({"suggestions": [item]}).to_domain()
    accepted, partial = validate_output(output, "Synthetic evidence")
    assert not partial and accepted[0]["value"]["title"] == "Engineer"
    assert validate_output(output, "Different source") == ([], True)


def test_dry_run_estimates_actual_sdk_serialization():
    import hashlib
    from app.evaluation import __main__ as evaluation
    from app.evaluation.fixtures import cases
    captured = []

    def transport(request):
        captured.append(request.content)
        return httpx.Response(200, json={
            "id": "offline", "object": "response", "created_at": 0,
            "model": evaluation.GROQ_MODEL, "status": "completed", "output": [],
        })

    source = cases()[0]["source"]
    with OpenAI(api_key="synthetic", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        provider = GroqResponsesProvider(api_key="unused", model=evaluation.GROQ_MODEL,
            timeout=evaluation.TIMEOUT, max_output_tokens=1500, client=evaluation.Meter(client))
        from app.services.ai_provider import ProviderFailure
        with pytest.raises(ProviderFailure):  # Empty mock result; request already serialized.
            provider.suggest(source["cv_text"])
    plan = evaluation.request_plan("profile", source, "groq", max_output_tokens=1500)
    assert len(captured) == 1
    assert json.loads(captured[0])["service_tier"] == "default"
    assert plan["sha256"] == hashlib.sha256(captured[0]).hexdigest()
    assert plan["input_token_estimate"] == len(captured[0]) + 2048
    assert plan["complete_token_estimate"] == len(captured[0]) + 2048 + 1500


def test_public_apply_selection_uses_title_only():
    from app.schemas.profile_suggestions import ApplySuggestionRequest
    item = suggestion("experience", {"title": "Engineer", "organization": "Synthetic"})
    parsed = ApplySuggestionRequest.model_validate({"selections": [item]})
    assert parsed.model_dump()["selections"][0]["value"]["title"] == "Engineer"
    item["value"]["job_title"] = item["value"].pop("title")
    with pytest.raises(ValidationError):
        ApplySuggestionRequest.model_validate({"selections": [item]})


def test_canonical_sdk_request_meets_documented_structural_requirements():
    """Check observable requirements, without claiming undocumented keyword support."""
    import hashlib
    from pathlib import Path
    from app.evaluation import __main__ as evaluation
    from app.evaluation.fixtures import cases
    from app.services.ai_provider import ProviderFailure
    captured = []

    def transport(request):
        captured.append(request)
        return httpx.Response(400, json={"error": {
            "type": "invalid_request_error", "code": "json_validate_failed"}})

    with OpenAI(api_key="synthetic", base_url="https://api.groq.com/openai/v1", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        provider = GroqResponsesProvider(api_key="unused", model=evaluation.GROQ_MODEL,
            timeout=60, max_output_tokens=1500, client=evaluation.Meter(client))
        with pytest.raises(ProviderFailure):
            provider.suggest(cases()[0]["source"]["cv_text"])
    assert len(captured) == 1  # HTTP 400 is never retried or sent to another provider.
    request = captured[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/responses"
    retained = Path(__file__).resolve().parents[2] / "evidence/groq-profile-request-offline-20260917.json"
    assert request.content == retained.read_bytes()
    plan = evaluation.build_plan("groq", pilot=True, task="profile")
    assert hashlib.sha256(request.content).hexdigest() == plan["requests"][0]["sha256"]
    payload = json.loads(request.content)
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["store"] is False and "tools" not in payload and not payload.get("stream")
    assert payload["service_tier"] == "default"
    assert payload["max_output_tokens"] == 1500
    assert payload["text"]["format"]["strict"] is True
    schema = payload["text"]["format"]["schema"]
    objects, refs = [], []

    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
                objects.append(node)
            if "$ref" in node:
                ref = node["$ref"]
                assert ref.startswith("#/$defs/")
                assert ref.removeprefix("#/$defs/") in schema["$defs"]
                refs.append(ref)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    assert len(objects) == 11 and len(refs) == 15
