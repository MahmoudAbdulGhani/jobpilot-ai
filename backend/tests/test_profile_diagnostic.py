"""Synthetic production-adapter evaluation; sockets always forbidden."""
import json
import socket

import httpx
import pytest

from app.evaluation import profile_diagnostic as diagnostic
from app.evaluation import __main__ as evaluation
from app.evaluation.fixtures import cases


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No live calls in diagnostic tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.delenv("JOBPILOT_GROQ_TPM", raising=False)
    monkeypatch.delenv("JOBPILOT_EVAL_ALLOW_LIVE", raising=False)
    monkeypatch.setattr(evaluation, "_load_dotenv", lambda: {})


def test_actual_profile_wire_keeps_evidence_bounds_and_all_strong_facts():
    payload = json.loads(diagnostic.prepared_request())
    schema = payload["text"]["format"]["schema"]
    assert payload["input"] == cases()[0]["source"]["cv_text"]
    assert payload["text"]["format"]["strict"] is True
    def dereference(node):
        if "$ref" in node:
            return schema["$defs"][node["$ref"].split("/")[-1]]
        return node
    branches = schema["properties"]["suggestions"]["items"]["anyOf"]
    for branch in branches:
        suggestion = dereference(branch)
        assert "evidence" in suggestion["required"]
        evidence = dereference(suggestion["properties"]["evidence"])
        assert evidence["minItems"] == 1 and evidence["maxItems"] == 10
        quote = dereference(evidence["items"])["properties"]["quote"]
        assert quote == {"type": "string", "minLength": 1, "maxLength": 1000}



@pytest.mark.parametrize("mode", ["success", "http_schema", "http_generated", "empty_list", "empty_quote", "unsupported_quote"])
def test_diagnostic_failure_boundaries_and_no_retry(tmp_path, monkeypatch, mode):
    dry, output = tmp_path / "dry.json", tmp_path / "result.json"
    assert diagnostic.main(["--output", str(dry)]) == 0
    plan = json.loads(dry.read_text())["plan"]
    calls = []
    suggestion = {"id": "headline-1", "field": "headline", "value": "Backend engineer",
                  "evidence": [{"quote": "Backend engineer"}]}
    if mode == "empty_list":
        suggestion["evidence"] = []
    if mode == "empty_quote":
        suggestion["evidence"][0]["quote"] = ""
    if mode == "unsupported_quote":
        suggestion["evidence"][0]["quote"] = "private-person private-token"
    generated = {"suggestions": [suggestion], "partial": False, "message": None}

    def transport(request):
        calls.append(request)
        if mode.startswith("http_"):
            message = ("Invalid schema: unsupported minLength" if mode == "http_schema" else
                       "Generated JSON does not match the expected schema. Please adjust your prompt.")
            return httpx.Response(400, json={"error": {
                "type": "invalid_request_error",
                "code": "invalid_json_schema" if mode == "http_schema" else "json_validate_failed",
                "message": message + " private-token Jane Doe jane@example.com 5551234567",
                "failed_generation": json.dumps({"suggestions": [dict(suggestion, evidence=[])]})
                    if mode == "http_generated" else None}})
        return httpx.Response(200, json={"id": "mock", "object": "response", "created_at": 0,
            "model": "openai/gpt-oss-20b", "status": "completed",
            "usage": {"input_tokens": 193, "output_tokens": 361, "total_tokens": 554},
            "output": [{"id": "msg", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(generated), "annotations": []}]}]})

    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "private-token")
    monkeypatch.setattr(diagnostic.logging, "disable", lambda *args: None)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    result = diagnostic.main(["--live", "--max-cost-usd", str(plan["max_estimated_cost_usd"]),
                              "--dry-report", str(dry), "--output", str(output)])
    assert result == (0 if mode == "success" else 1)
    report = json.loads(output.read_text())
    assert report["actual_request_count"] == report["attempted_requests"] == len(calls) == 1
    row, capture = report["results"][0], report["synthetic_diagnostic"]
    assert capture["http_status"] == (400 if mode.startswith("http_") else 200)
    if mode == "success":
        assert row["status"] == "contract_pass" and row["checks"] == {"partial": False, "empty": False}
    elif mode.startswith("http_"):
        assert row["status"] == "provider_failure"
        assert "Invalid schema" in capture["provider_explanation"]["text"] if mode == "http_schema" else "Generated JSON" in capture["provider_explanation"]["text"]
        if mode == "http_generated":
            assert capture["failed_generation"]["supplied"]
            assert capture["failed_generation_local_parse"] == "failed"
            assert capture["failed_generation_validation"]["validation"]["errors"]
    elif mode == "unsupported_quote":
        assert row["status"] == "validation_failure"
    else:
        assert row["status"] == "provider_failure"
        assert row["validation"]["errors"]
        assert capture["usage"]["input_tokens"] == 193  # Even when SDK parse hides usage.
    serialized = output.read_text()
    for secret in ("private-token", "private-person", "Jane", "Doe", "jane@example.com", "5551234567"):
        assert secret not in serialized


def test_redaction_bounds_and_second_attempt_guard():
    value = diagnostic.redacted('private-token ' * 10000, 2048, ['private-token'])
    assert len(value["text"]) <= 2048 and value["truncated"]
    request = diagnostic.prepared_request()
    import hashlib
    transport = diagnostic.SyntheticTransport(httpx.MockTransport(lambda r: httpx.Response(400, json={})),
                                              hashlib.sha256(request).hexdigest())
    with httpx.Client(transport=transport) as client:
        client.post("https://api.groq.com/openai/v1/responses", content=request)
        with pytest.raises(RuntimeError, match="exactly one"):
            client.post("https://api.groq.com/openai/v1/responses", content=request)
    assert transport.count == 1


def test_live_requires_matching_budget_and_saved_dry_report(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: pytest.fail("No transport allowed"))
    for budget in ("0.000640", "0.000922"):
        with pytest.raises(SystemExit):
            diagnostic.main(["--live", "--max-cost-usd", budget, "--output", str(tmp_path / "none.json")])


def expand_schema(node, root):
    """Expand local references to compare validation semantics, not ref labels."""
    if isinstance(node, dict):
        if "$ref" in node:
            target = root
            for key in node["$ref"].removeprefix("#/").split("/"):
                target = target[key]
            node = {**target, **{key: value for key, value in node.items() if key != "$ref"}}
        return {key: expand_schema(value, root) for key, value in node.items() if key != "$defs"}
    if isinstance(node, list):
        return [expand_schema(item, root) for item in node]
    return node


def test_optimized_schema_is_equivalent_and_reserves_more_completion():
    from pathlib import Path
    previous = json.loads((Path(__file__).resolve().parents[2] /
        "evidence/groq-profile-evidence-bounds-request.json").read_bytes())
    proposed = json.loads(diagnostic.prepared_request())
    before, after = previous["text"]["format"]["schema"], proposed["text"]["format"]["schema"]
    assert expand_schema(before, before) == expand_schema(after, after)
    assert proposed["input"] == previous["input"]
    assert proposed["instructions"] == previous["instructions"]
    assert proposed["reasoning"] == {"effort": "low"}
    assert "reasoning_effort" not in proposed  # Chat parameter must not be guessed for Responses.
    assert proposed["max_output_tokens"] == 2250 > previous["max_output_tokens"]
    plan = evaluation.build_plan("groq", pilot=True, task="profile")
    assert plan["requests"][0]["complete_token_estimate"] <= 8000
    assert plan["requests"][0]["input_token_estimate"] == len(diagnostic.prepared_request()) + 2048


def truncated_generation():
    # Reconstruct the retained failed generation using safe synthetic IDs.
    # It has all three observed suggestions but lacks wire-required root keys.
    return {"suggestions": [
        {"id": "h1", "field": "headline", "value": "Backend engineer", "evidence": [{"quote": "Backend engineer"}]},
        {"id": "l1", "field": "location", "value": "Beirut", "evidence": [{"quote": "Location: Beirut"}]},
        {"id": "s1", "field": "skills", "value": "Python, PostgreSQL", "evidence": [{"quote": "Skills: Python, PostgreSQL"}]},
    ]}


@pytest.mark.parametrize("http_status", [200, 400])
def test_retained_truncation_cannot_become_full_pass_via_defaults(tmp_path, monkeypatch, http_status):
    dry, output = tmp_path / "dry.json", tmp_path / "result.json"
    diagnostic.main(["--output", str(dry)])
    plan = json.loads(dry.read_text())["plan"]
    generation = json.dumps(truncated_generation())
    calls = []
    def transport(request):
        calls.append(request)
        if http_status == 400:
            return httpx.Response(400, json={"error": {"type": "invalid_request_error",
                "code": "json_validate_failed", "failed_generation": generation,
                "message": "max completion tokens reached before generating a valid document: the output was truncated. missing properties: 'partial', 'message'"}})
        return httpx.Response(200, json={"id": "mock", "object": "response", "created_at": 0,
            "model": "openai/gpt-oss-20b", "status": "completed", "output": [
                {"id": "msg", "type": "message", "role": "assistant", "status": "completed", "content": [
                    {"type": "output_text", "text": generation, "annotations": []}]}]})
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic")
    monkeypatch.setattr(diagnostic.logging, "disable", lambda *args: None)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    assert diagnostic.main(["--live", "--max-cost-usd", str(plan["max_estimated_cost_usd"]),
        "--dry-report", str(dry), "--output", str(output)]) == 1
    report = json.loads(output.read_text())
    assert len(calls) == report["actual_request_count"] == 1
    assert report["results"][0]["status"] == "provider_failure"
    if http_status == 400:
        capture = report["synthetic_diagnostic"]
        assert "max completion tokens reached" in capture["provider_explanation"]["text"]
        assert capture["failed_generation_local_parse"] == "failed"
        errors = capture["failed_generation_validation"]["validation"]["errors"]
        assert "failed_generation_checks" not in capture
    else:
        errors = report["results"][0]["validation"]["errors"]
    assert {(e["type"], tuple(e["location"])) for e in errors} == {
        ("missing", ("partial",)), ("missing", ("message",))}


def test_nested_required_wire_fields_cannot_be_defaulted():
    from app.schemas.profile_suggestions import GroqProfileOutput
    from pydantic import ValidationError
    item = {"id": "e1", "field": "experience", "value": {"job_title": "Engineer", "organization": "Cedar Demo"},
            "evidence": [{"quote": "Engineer at Cedar Demo"}]}
    payload = {"suggestions": [item], "partial": False, "message": None}
    with pytest.raises(ValidationError) as caught:
        GroqProfileOutput.model_validate(payload)
    assert {error["loc"] for error in caught.value.errors()} == {
        ("suggestions", 0, "value", "period"), ("suggestions", 0, "value", "notes")}
    item["value"].update(period=None, notes=None)
    assert GroqProfileOutput.model_validate(payload).to_domain().suggestions[0].value.title == "Engineer"


@pytest.mark.parametrize("provider_name,task", [("openai", "profile"), ("groq", "fit"), ("openai", "pack")])
def test_other_ai_capabilities_do_not_get_profile_reasoning_or_schema(provider_name, task):
    from app.services.ai_provider import OpenAIResponsesProvider, GroqResponsesProvider, ProviderFailure
    from openai import OpenAI
    calls = []
    def transport(request):
        calls.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
    with OpenAI(api_key="synthetic", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        cls = GroqResponsesProvider if provider_name == "groq" else OpenAIResponsesProvider
        provider = cls(api_key="unused", model="openai/gpt-oss-20b", timeout=60, max_output_tokens=1500, client=client)
        with pytest.raises(ProviderFailure):
            evaluation.dispatch(provider, task, cases()[0]["source"])
    assert len(calls) == 1 and "reasoning" not in calls[0]
    assert calls[0]["max_output_tokens"] == 1500
    assert calls[0]["text"]["format"].get("name") != "GroqProfileOutput"
    if provider_name == "openai" and task == "profile":
        assert calls[0]["text"]["format"] == {"type": "json_object"}
        assert "schema" not in calls[0]["text"]


def test_schema_compression_never_merges_different_evidence_constraints():
    from pydantic import BaseModel, Field

    from app.schemas.profile_suggestions import (
        GroqProfileOutput, ProviderWireSuggestionOutput, _groq_profile_schema,
        _strict_wire_schema,
    )

    class Short(BaseModel):
        evidence: list[dict] = Field(min_length=1)

    class Long(BaseModel):
        evidence: list[dict] = Field(min_length=2)

    class Envelope(BaseModel):
        short: Short
        long: Long

    with pytest.raises(ValueError, match="different constraints"):
        _groq_profile_schema(Envelope.model_json_schema())
    # The real Groq union schema still shares its identical evidence arrays,
    # and the flat OpenAI schema is already fully strict single-shape output.
    assert _groq_profile_schema(GroqProfileOutput.model_json_schema())
    flat = ProviderWireSuggestionOutput.model_json_schema()
    for node in flat["$defs"].values():
        if "properties" in node:
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
    assert _strict_wire_schema(flat) == flat
