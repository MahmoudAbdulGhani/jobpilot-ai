"""Offline regressions for the provider-only job_title compatibility workaround."""
import json
import socket

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.evaluation.validation_diagnostics import validation_diagnostics
from app.schemas.profile import CandidateProfileUpdate, CandidateProfileResponse
from app.schemas.profile_suggestions import ALL_SUGGESTION_FIELDS, ProviderSuggestionOutput, ProviderWireSuggestionOutput, _compact_wire_schema
from app.services.ai_provider import GroqResponsesProvider, OpenAIResponsesProvider


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No network permitted")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def suggestion(field, value):
    return {"id": "synthetic", "field": field, "value": value,
            "evidence": [{"quote": "Synthetic evidence"}]}


def wire_suggestion(field, bucket):
    return {"id": "synthetic", "field": field, "value": bucket,
            "evidence": [{"quote": "Synthetic evidence"}]}


def complete_wire(suggestions):
    present = {item["field"] for item in suggestions}
    return {
        "suggestions": suggestions,
        "not_found": sorted(ALL_SUGGESTION_FIELDS - present),
        "partial": False,
        "message": None,
    }


def test_serialized_sdk_requires_job_title_and_maps_to_domain_title():
    captured = []

    def transport(request):
        captured.append(json.loads(request.content)["text"]["format"])
        return httpx.Response(200, json={
            "id": "offline", "object": "response", "created_at": 0,
            "model": "synthetic", "status": "completed",
            "output": [{"id": "msg", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "annotations": [], "text": json.dumps(complete_wire([
                            wire_suggestion("experience", {
                                "experience": {"job_title": "Engineer", "organization": "Synthetic",
                                               "period": None, "notes": None}})]))}]}],
        })

    with OpenAI(api_key="synthetic", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        output = OpenAIResponsesProvider(api_key="unused", model="synthetic", timeout=3,
                              max_output_tokens=1500, client=client).suggest("Synthetic evidence")
    assert output.suggestions[0].value.title == "Engineer"
    assert "job_title" not in output.model_dump()["suggestions"][0]["value"]
    assert len(captured) == 1
    assert captured[0] == {
        "type": "json_schema",
        "name": "ProviderWireSuggestionOutput",
        "schema": ProviderWireSuggestionOutput.model_json_schema(),
        "strict": True,
    }
    local = ProviderSuggestionOutput.model_json_schema()
    compact = ProviderWireSuggestionOutput.model_json_schema()
    wire = compact
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
        # The OpenAI wire contract is one flat suggestion with strict objects;
        # the suggestion-level anyOf union (rejected by strict structured
        # outputs) is gone, so only nullable anyOf remains on the wire.
        assert schema["properties"]["suggestions"]["items"]["$ref"] == (
            "#/$defs/ProviderWireSuggestion")
        suggestion = schema["$defs"]["ProviderWireSuggestion"]
        assert set(suggestion["required"]) == {"id", "field", "evidence", "value"}
        assert suggestion["additionalProperties"] is False
        assert set(suggestion["properties"]["field"]["enum"]) == set(ALL_SUGGESTION_FIELDS)
        value = schema["$defs"]["ProviderWireValue"]
        assert set(value["required"]) == set(value["properties"])
        assert value["additionalProperties"] is False
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


def test_missing_experience_title_reproduces_all_retained_errors():
    payload = {"suggestions": [suggestion("headline", "Synthetic") for _ in range(3)] + [
        suggestion("experience", {"organization": "Synthetic", "period": None, "notes": None})]}
    with pytest.raises(ValidationError) as caught:
        ProviderSuggestionOutput.model_validate_json(json.dumps(payload))
    diagnostic = validation_diagnostics(caught.value)["validation"]
    actual = {(e["type"], tuple(e["loc"][2:])) for e in
              caught.value.errors(include_input=False, include_context=False, include_url=False)}
    # Complete retained error signature, without any original input values.
    expected = {
        ("missing", ("ExperienceSuggestion", "value", "title")),
        ("extra_forbidden", ("EducationSuggestion", "value", "organization")),
        ("extra_forbidden", ("EducationSuggestion", "value", "notes")),
        ("missing", ("EducationSuggestion", "value", "school")),
        ("missing", ("LanguageSuggestion", "value", "name")),
        ("missing", ("LanguageSuggestion", "value", "proficiency")),
    }
    for branch in ("HeadlineSuggestion", "LocationSuggestion", "TargetRoleSuggestion"):
        expected.add(("string_type", (branch, "value")))
    expected.add(("list_type", ("SkillsSuggestion", "value")))
    for branch in ("HeadlineSuggestion", "LocationSuggestion", "TargetRoleSuggestion", "SkillsSuggestion",
                   "EducationSuggestion", "LanguageSuggestion", "RemotePreferenceSuggestion",
                   "WorkAuthorizationSuggestion", "SalaryPreferenceSuggestion"):
        expected.add(("literal_error", (branch, "field")))
    for field in ("organization", "period", "notes"):
        expected.add(("extra_forbidden", ("LanguageSuggestion", "value", field)))
        expected.add(("extra_forbidden", ("SalaryPreferenceSuggestion", "value", field)))
    for branch in ("RemotePreferenceSuggestion", "WorkAuthorizationSuggestion"):
        expected.add(("literal_error", (branch, "value")))
    assert actual == expected
    assert len(actual) == 27
    assert len(diagnostic["errors"]) == 20 and diagnostic["errors_truncated"]
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
    payload = complete_wire([{
        "id": "exp-1", "field": "experience",
        "value": {"experience": {"job_title": "Engineer", "organization": "Cedar Demo",
                                 "period": None, "notes": None}},
        "evidence": [{"quote": "Engineer at Cedar Demo"}]}])
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
        ProviderWireSuggestionOutput.model_validate(complete_wire([
            wire_suggestion("experience", {"experience": entry})]))


@pytest.mark.parametrize("missing", ["job_title", "organization"])
def test_provider_entry_requires_fields(missing):
    entry = {"job_title": "Engineer", "organization": "Synthetic"}
    del entry[missing]
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([
            wire_suggestion("experience", {"experience": entry})]))


@pytest.mark.parametrize("evidence", [[], [{"quote": ""}], [{"quote": "x" * 1001}]])
def test_provider_evidence_constraints(evidence):
    item = wire_suggestion("experience", {"experience": {"job_title": "Engineer", "organization": "Synthetic"}})
    item["evidence"] = evidence
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([item]))


def test_mapped_experience_preserves_evidence_validation():
    from app.services.profile_suggestion_service import validate_output
    item = wire_suggestion("experience", {"experience": {"job_title": "Engineer", "organization": "Synthetic"}})
    item["evidence"] = [{"quote": "Engineer Synthetic"}]
    output = ProviderWireSuggestionOutput.model_validate(complete_wire([item])).to_domain()
    accepted, partial = validate_output(output, "Engineer Synthetic")
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
            timeout=60, max_output_tokens=evaluation.GROQ_PROFILE_MAX_OUTPUT_TOKENS, client=evaluation.Meter(client))
        with pytest.raises(ProviderFailure):
            provider.suggest(cases()[0]["source"]["cv_text"])
    assert len(captured) == 1  # HTTP 400 is never retried or sent to another provider.
    request = captured[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/responses"
    retained = Path(__file__).resolve().parents[2] / "evidence/groq-profile-evidence-bounds-request.json"
    assert json.loads(request.content)["input"] == json.loads(retained.read_bytes())["input"]
    plan = evaluation.build_plan("groq", pilot=True, task="profile")
    assert hashlib.sha256(request.content).hexdigest() == plan["requests"][0]["sha256"]
    payload = json.loads(request.content)
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["store"] is False and "tools" not in payload and not payload.get("stream")
    assert payload["service_tier"] == "default"
    assert payload["max_output_tokens"] == evaluation.GROQ_PROFILE_MAX_OUTPUT_TOKENS
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
    assert len(objects) == 11 and len(refs) == 16


@pytest.mark.parametrize("evidence,outcome", [
    ([{"quote": "Backend engineer"}], "accepted"),
    ([], "parse_failure"),
    ([{"quote": ""}], "parse_failure"),
    ([{"quote": "Unsupported passage"}], "evidence_failure"),
])
def test_supported_headline_requires_nonempty_exact_source_quote(evidence, outcome):
    from app.services.profile_suggestion_service import validate_output
    source = "Backend engineer"
    item = wire_suggestion("headline", {"text": source})
    item["evidence"] = evidence
    payload = complete_wire([item])
    if outcome == "parse_failure":
        with pytest.raises(ValidationError):
            ProviderWireSuggestionOutput.model_validate(payload)
        return
    output = ProviderWireSuggestionOutput.model_validate(payload).to_domain()
    accepted, partial = validate_output(output, source)
    if outcome == "accepted":
        assert not partial and len(accepted) == 1
        assert accepted[0]["value"] == source
        assert accepted[0]["evidence"] == [{"quote": source}]
    else:
        assert accepted == [] and partial


def test_next_diagnostic_only_closes_empty_string_schema_gap():
    from pathlib import Path
    evidence_dir = Path(__file__).resolve().parents[2] / "evidence"
    original = json.loads((evidence_dir / "groq-profile-minimal-probe-request.json").read_bytes())
    prepared = json.loads((evidence_dir / "groq-profile-nonempty-evidence-probe-request.json").read_bytes())
    assert original["input"] == "Backend engineer"
    assert "quote its exact supporting evidence" in original["instructions"]
    old_evidence = original["text"]["format"]["schema"]["properties"]["evidence"]
    assert old_evidence == {"type": "string"}  # No evidence list in the diagnostic.
    new_evidence = prepared["text"]["format"]["schema"]["properties"]["evidence"]
    assert new_evidence.pop("minLength") == 1
    assert prepared == original  # No prompt/source/model change or injected evidence.


def test_all_ten_categories_parse_from_the_flat_wire_and_convert_to_domain():
    suggestions = [
        {"id": "headline-1", "field": "headline", "value": {"text": "Backend engineer"},
         "evidence": [{"quote": "Backend engineer"}]},
        {"id": "location-1", "field": "location", "value": {"text": "Beirut, Lebanon"},
         "evidence": [{"quote": "Location: Beirut, Lebanon"}]},
        {"id": "role-1", "field": "target_roles", "value": {"text": "Backend engineer"},
         "evidence": [{"quote": "Target role: Backend engineer"}]},
        {"id": "skill-1", "field": "skills", "value": {"skills": ["Python", "PostgreSQL"]},
         "evidence": [{"quote": "Skills: Python, PostgreSQL"}]},
        {"id": "exp-1", "field": "experience",
         "value": {"experience": {"job_title": "Engineer", "organization": "Cedar Demo"}},
         "evidence": [{"quote": "Engineer at Cedar Demo"}]},
        {"id": "edu-1", "field": "education",
         "value": {"education": {"school": "Example University", "degree": "BSc"}},
         "evidence": [{"quote": "BSc at Example University"}]},
        {"id": "lang-1", "field": "languages",
         "value": {"language": {"name": "French", "proficiency": "professional"}},
         "evidence": [{"quote": "Fluent French"}]},
        {"id": "remote-1", "field": "remote_preference", "value": {"remote_preference": "remote"},
         "evidence": [{"quote": "Remote preference: remote"}]},
        {"id": "auth-1", "field": "work_authorization", "value": {"work_authorization": "citizen"},
         "evidence": [{"quote": "Work authorization: citizen"}]},
        {"id": "sal-1", "field": "salary_preference",
         "value": {"salary": {"currency": "USD", "min": 70000, "max": 90000}},
         "evidence": [{"quote": "Salary: USD 70000 to 90000"}]},
    ]
    parsed = ProviderWireSuggestionOutput.model_validate(complete_wire(suggestions))
    domain = parsed.to_domain()
    assert [item.field for item in domain.suggestions] == [
        "headline", "location", "target_roles", "skills", "experience", "education",
        "languages", "remote_preference", "work_authorization", "salary_preference"]
    assert domain.not_found == []
    by_field = {item.field: item for item in domain.suggestions}
    assert by_field["headline"].value == "Backend engineer"
    assert by_field["location"].value == "Beirut, Lebanon"
    assert by_field["target_roles"].value == "Backend engineer"
    assert by_field["skills"].value == ["Python", "PostgreSQL"]
    assert by_field["experience"].value.title == "Engineer"
    assert by_field["experience"].value.organization == "Cedar Demo"
    assert by_field["education"].value.school == "Example University"
    assert by_field["languages"].value.proficiency == "professional"
    assert by_field["remote_preference"].value == "remote"
    assert by_field["work_authorization"].value == "citizen"
    assert by_field["salary_preference"].value.min == 70000
    assert by_field["salary_preference"].value.max == 90000


def test_missing_languages_become_not_found_in_the_domain_output():
    fields = ["headline", "location", "target_roles", "skills", "experience",
              "education", "remote_preference", "work_authorization", "salary_preference"]
    suggestions = []
    for field in fields:
        if field == "experience":
            value = {"experience": {"job_title": "Engineer", "organization": "Cedar"}}
        elif field == "education":
            value = {"education": {"school": "Example University"}}
        elif field == "remote_preference":
            value = {"remote_preference": "remote"}
        elif field == "work_authorization":
            value = {"work_authorization": "citizen"}
        elif field == "salary_preference":
            value = {"salary": {"currency": "USD", "min": 50000, "max": 80000}}
        elif field == "skills":
            value = {"skills": ["Python"]}
        else:
            value = {"text": "Backend engineer"}
        suggestions.append({"id": f"{field}-1", "field": field, "value": value,
                            "evidence": [{"quote": "Synthetic evidence"}]})
    payload = complete_wire(suggestions)
    payload["not_found"] = ["languages"]
    domain = ProviderWireSuggestionOutput.model_validate(payload).to_domain()
    assert [item.field for item in domain.suggestions] == fields
    assert domain.not_found == ["languages"]


def test_skills_experience_education_parse_from_their_typed_buckets():
    payload = complete_wire([
        {"id": "skill-1", "field": "skills", "value": {"skills": ["Python", "PostgreSQL"]},
         "evidence": [{"quote": "Skills: Python, PostgreSQL"}]},
        {"id": "exp-1", "field": "experience",
         "value": {"experience": {"job_title": "Engineer", "organization": "Cedar Demo",
                                  "period": "2021-2024", "notes": "Core platform"}},
         "evidence": [{"quote": "Engineer at Cedar Demo"}]},
        {"id": "edu-1", "field": "education",
         "value": {"education": {"school": "Example University", "degree": "BSc",
                                 "field": "Computer Science", "period": "2020"}},
         "evidence": [{"quote": "BSc Computer Science at Example University"}]},
    ])
    domain = ProviderWireSuggestionOutput.model_validate(payload).to_domain()
    values = {item.field: item.value for item in domain.suggestions}
    assert values["skills"] == ["Python", "PostgreSQL"]
    assert values["experience"].title == "Engineer"
    assert values["experience"].notes == "Core platform"
    assert values["education"].degree == "BSc"
    assert values["education"].field == "Computer Science"


def test_wire_rejects_mismatched_multiple_or_missing_value_buckets():
    mismatch = wire_suggestion("experience", {"text": "Engineer at Cedar"})
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([mismatch]))
    two_buckets = wire_suggestion("headline", {"text": "Engineer", "salary": {"currency": "USD"}})
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([two_buckets]))
    no_bucket = wire_suggestion("headline", {})
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([no_bucket]))


def test_invalid_claims_are_rejected_by_the_local_contract():
    # 250 chars fits the flat wire text bound (300) but violates the domain
    # headline bound (200); the wire parse succeeds and the domain conversion
    # revalidates, the exact boundary the production response-validation
    # mapping covers.
    headline = wire_suggestion("headline", {"text": "x" * 250})
    parsed = ProviderWireSuggestionOutput.model_validate(complete_wire([headline]))
    with pytest.raises(ValidationError):
        parsed.to_domain()
    invalid_salary = wire_suggestion(
        "salary_preference", {"salary": {"currency": "USD", "min": 90000, "max": 50000}})
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([invalid_salary]))
    invalid_remote = wire_suggestion("remote_preference", {"remote_preference": "onsite"})
    with pytest.raises(ValidationError):
        ProviderWireSuggestionOutput.model_validate(complete_wire([invalid_remote]))


def test_openai_provider_maps_out_of_contract_wire_content_to_invalid_field_value():
    from types import SimpleNamespace

    from app.services.ai_provider import OpenAIResponsesProvider, ProviderFailure
    payload = complete_wire([wire_suggestion("headline", {"text": "x" * 250})])
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        status="completed", output_text=json.dumps(payload))))
    provider = OpenAIResponsesProvider(
        api_key="unused", model="synthetic", timeout=3,
        max_output_tokens=1500, client=client,
    )
    with pytest.raises(ProviderFailure) as caught:
        provider.suggest("private CV text")
    assert caught.value.category == "invalid_field_value" == str(caught.value)
    assert caught.value.field == "headline"
    assert "private CV text" not in str(caught.value)
