"""Offline regression for schema metadata colliding with an actual title field."""
import json
import socket

import httpx
import pytest
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.evaluation.validation_diagnostics import validation_diagnostics
from app.schemas.profile_suggestions import ProviderSuggestionOutput, _compact_wire_schema
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


def test_serialized_sdk_schema_preserves_title_and_all_discriminators():
    captured = []

    def transport(request):
        captured.append(json.loads(request.content)["text"]["format"])
        return httpx.Response(200, json={
            "id": "offline", "object": "response", "created_at": 0,
            "model": "synthetic", "status": "completed",
            "output": [{"id": "msg", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "annotations": [], "text": '{"suggestions":[]}'}]}],
        })

    with OpenAI(api_key="synthetic", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        GroqResponsesProvider(api_key="unused", model="synthetic", timeout=3,
                              max_output_tokens=1500, client=client).suggest("Synthetic evidence")
    assert len(captured) == 1
    assert captured[0]["strict"] is True
    local = BaseModel.model_json_schema.__func__(ProviderSuggestionOutput)
    compact = ProviderSuggestionOutput.model_json_schema()
    wire = captured[0]["schema"]
    variants = {"HeadlineSuggestion": "headline", "LocationSuggestion": "location",
                "SkillsSuggestion": "skills", "ExperienceSuggestion": "experience",
                "EducationSuggestion": "education", "LanguageSuggestion": "languages"}
    for schema in (local, compact, wire):
        entry = schema["$defs"]["ExperienceEntry"]
        assert "title" in entry["required"]
        assert entry["properties"]["title"]["type"] == "string"
        assert entry["properties"]["title"]["minLength"] == 1
        assert entry["properties"]["title"]["maxLength"] == 200
        assert entry["additionalProperties"] is False
        assert schema["$defs"]["ExperienceSuggestion"]["properties"]["value"] == {"$ref": "#/$defs/ExperienceEntry"}
        assert {item["$ref"] for item in schema["properties"]["suggestions"]["items"]["anyOf"]} == {
            f"#/$defs/{variant}" for variant in variants}
        for variant, literal in variants.items():
            branch = schema["$defs"][variant]
            assert "field" in branch["required"]
            assert branch["properties"]["field"]["const"] == literal


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
