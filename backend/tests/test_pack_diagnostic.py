"""Pack preparation and single-attempt diagnostics; all network access blocked."""
import json
import socket
import httpx
import pytest
from app.evaluation import profile_diagnostic as diagnostic
from app.evaluation import __main__ as evaluation
from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No live calls")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.delenv("JOBPILOT_GROQ_TPM", raising=False)
    monkeypatch.setattr(evaluation, "_load_dotenv", lambda: {})

def test_pack_serialization_preserves_production_contract():
    payload = json.loads(diagnostic.prepared_request("pack"))
    assert json.loads(payload["input"]) == cases()[0]["source"]
    assert payload["max_output_tokens"] == evaluation.GROQ_PACK_MAX_OUTPUT_TOKENS == 1664
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["name"] == "GroqPackOutput"
    plan = evaluation.build_plan("groq", pilot=True, task="pack")
    assert plan["max_requests"] == 1 and plan["retries"] == 0
    assert plan["requests"][0]["input_token_estimate"] == len(diagnostic.prepared_request("pack")) + 2048
    assert plan["requests"][0]["complete_token_estimate"] <= 8000

@pytest.mark.parametrize("provider_name", ["groq", "openai"])
@pytest.mark.parametrize("mode", ["success", "structural_labels", "missing_notes", "missing_nullable", "missing_letter", "truncated", "incomplete", "empty_evidence", "unsupported_quote", "http_schema", "http_generation"])
def test_pack_diagnostic_acceptance_and_safe_capture(tmp_path, monkeypatch, mode, provider_name):
    dry, result = tmp_path / "dry.json", tmp_path / "result.json"
    diagnostic.main(["--provider", provider_name, "--task", "pack", "--output", str(dry)])
    plan = json.loads(dry.read_text())["plan"]
    output = DeterministicTestProvider().create_pack(cases()[0]["source"]).model_dump(mode="json")
    if mode == "structural_labels":
        output["cv"]["blocks"].insert(1, {"id": "contact-label", "kind": "paragraph", "text": "Contact", "evidence": []})
        output["cover_letter"]["blocks"].insert(1, {"id": "subject", "kind": "paragraph", "text": "Application for Backend Engineer", "evidence": []})
    if mode == "missing_notes": output.pop("review_notes")
    if mode == "missing_nullable": output["cv"]["blocks"][1]["evidence"][0].pop("fact_id")
    if mode == "missing_letter": output.pop("cover_letter")
    if mode == "empty_evidence": output["cv"]["blocks"][1]["evidence"] = []
    if mode == "unsupported_quote": output["cv"]["blocks"][1]["evidence"][0]["cv_quote"] = "private-person private-token"
    generation = json.dumps(output)
    if mode == "truncated": generation = generation[:-10]
    calls = []
    def transport(request):
        calls.append(request)
        expected_url = "https://api.openai.com/v1/responses" if provider_name == "openai" else "https://api.groq.com/openai/v1/responses"
        assert str(request.url) == expected_url
        if provider_name == "openai":
            assert json.loads(request.content)["reasoning"] == {"effort": "minimal"}
        if mode.startswith("http_"):
            return httpx.Response(400, json={"error": {"type": "invalid_request_error",
                "code": "invalid_json_schema" if mode == "http_schema" else "json_validate_failed",
                "message": "schema invalid private-token secret@example.test",
                "failed_generation": generation[:-10] if mode == "http_generation" else None}})
        return httpx.Response(200, json={"id": "mock", "object": "response", "created_at": 0,
            "model": "openai/gpt-oss-20b", "status": "incomplete" if mode == "incomplete" else "completed",
            "incomplete_details": {"reason": "max_output_tokens"} if mode == "incomplete" else None,
            "output": [{"id": "msg", "type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": generation, "annotations": []}]}]})
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic")
    monkeypatch.setenv("JOBPILOT_OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(diagnostic.logging, "disable", lambda *args: None)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    code = diagnostic.main(["--provider", provider_name, "--task", "pack", "--live", "--max-cost-usd", str(plan["max_estimated_cost_usd"]), "--dry-report", str(dry), "--output", str(result)])
    report = json.loads(result.read_text())
    assert len(calls) == report["actual_request_count"] == 1
    assert (code == 0) == (mode in ("success", "structural_labels"))
    assert (report["results"][0]["status"] == "contract_pass") == (mode in ("success", "structural_labels"))
    assert "private-token" not in result.read_text() and "secret@example.test" not in result.read_text()
    if mode == "structural_labels":
        row = report["results"][0]
        assert row["structural_labels_corrected"] is True
        normalized = json.loads(row["output_redacted"]["text"])
        assert normalized["cv"]["blocks"][1]["kind"] == "heading"
        assert len(normalized["cover_letter"]["blocks"]) == len(output["cover_letter"]["blocks"]) - 1
    if mode in ("missing_notes", "missing_nullable"):
        assert report["synthetic_diagnostic"]["returned_generation_local_parse"] == "failed"
    if mode == "incomplete":
        assert report["synthetic_diagnostic"]["provider_status"] == "incomplete"
        assert report["synthetic_diagnostic"]["incomplete_reason"]["text"] == "max_output_tokens"
    if mode == "http_generation":
        assert report["synthetic_diagnostic"]["failed_generation_local_parse"] == "failed"


def test_compact_pack_schema_preserves_every_validation_keyword():
    from pathlib import Path
    previous = json.loads((Path(__file__).resolve().parents[2] /
        "evidence/groq-pack-strong-dry-20260917.json").read_text())["request"]
    proposed = json.loads(diagnostic.prepared_request("pack"))
    def without_annotations(node):
        if isinstance(node, dict):
            return {key: without_annotations(value) for key, value in node.items() if key != "title"}
        if isinstance(node, list):
            return [without_annotations(value) for value in node]
        return node
    assert proposed["text"]["format"]["schema"] == without_annotations(previous["text"]["format"]["schema"])
    assert "application-pack-v2" == evaluation.PACK_PROMPT_VERSION
    assert "Keep each career fact associated only" in proposed["instructions"]
    assert "Never combine separately supported facts" in proposed["instructions"]
    assert "exact contiguous source excerpts" in proposed["instructions"]
    assert "evidence-free body kind" in proposed["instructions"]
    assert proposed["input"] == previous["input"]
    plan = evaluation.build_plan("groq", pilot=True, task="pack")
    assert plan["requests"][0]["complete_token_estimate"] == 8000
    assert plan["requests"][0]["max_output_tokens"] > 1500
    # The persisted baseline is also the exact OpenAI pack contract (no compaction).
    from app.services.ai_provider import OpenAIResponsesProvider, ProviderFailure
    from openai import OpenAI
    captured = []
    def transport(request):
        captured.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
    with OpenAI(api_key="synthetic", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        provider = OpenAIResponsesProvider(api_key="unused", model="gpt-5-mini", timeout=60, max_output_tokens=1500, client=client)
        with pytest.raises(ProviderFailure):
            provider.create_pack(cases()[0]["source"])
    assert captured[0]["text"] == previous["text"]
    assert "reasoning" not in captured[0]


def test_metadata_compaction_preserves_actual_title_property():
    from app.schemas.application_packs import GroqPackOutput
    class WithTitle(GroqPackOutput):
        title: str
    schema = WithTitle.model_json_schema()
    assert schema["properties"]["title"] == {"type": "string"}
    assert "title" in schema["required"]


@pytest.mark.parametrize("document,index", [("cv", 1), ("cover_letter", 1)])
def test_retained_joined_quote_is_rejected_even_with_valid_fact_id(document, index):
    from app.services.application_pack_service import validate_generated, PackError
    source = cases()[0]["source"]
    output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
    # Exact offending quote is recoverable from retained redaction + synthetic fact.
    joined = source["profile_facts"][3]["value"]
    assert joined == "Engineer at Cedar Demo, 2021-2024; built a booking API"
    assert joined not in source["cv_text"]
    output[document]["blocks"][index]["evidence"] = [{"fact_id": "fact-4", "cv_quote": joined}]
    with pytest.raises(PackError, match="unsupported CV passage"):
        validate_generated(output, source)

@pytest.mark.parametrize("text", ["Alex Example\nalex@example.test", "English", "I have strong technical skills.", "Thank you for your consideration."])
def test_body_evidence_rule_has_no_factual_or_courtesy_bypass(text):
    from app.services.application_pack_service import validate_generated, PackError
    source = cases()[0]["source"]
    output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
    # Contacts are retained verbatim. Other texts are synthetic boundary examples,
    # not reconstructions of the redacted language/closing text.
    output["cover_letter"]["blocks"][1].update(text=text, evidence=[])
    with pytest.raises(PackError, match="missing source evidence"):
        validate_generated(output, source)


def test_separate_exact_excerpts_and_saved_fact_reference_pass_without_repair():
    from app.services.application_pack_service import validate_generated
    source = cases()[0]["source"]
    output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
    evidence = [{"fact_id": None, "cv_quote": "Engineer at Cedar Demo, 2021-2024"},
                {"fact_id": None, "cv_quote": "Project: built a booking API"},
                {"fact_id": "fact-4", "cv_quote": None}]
    output["cv"]["blocks"][1].update(text="Engineer at Cedar Demo, 2021-2024; built a booking API", evidence=evidence)
    parsed = validate_generated(output, source)
    assert [e.model_dump() for e in parsed.cv.blocks[1].evidence] == evidence


def test_unsupported_relationship_still_needs_semantic_review():
    from app.services.application_pack_service import validate_generated, PackError
    source = cases()[0]["source"]
    output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
    # Fail-closed: valid references cannot prove a join. The draft is rejected
    # so it is never ready, and the user must review the source first.
    output["cover_letter"]["blocks"][1].update(
        text="I built the booking API using Python and PostgreSQL.",
        evidence=[{"fact_id": f"fact-{n}", "cv_quote": None} for n in (2, 3, 4)])
    with pytest.raises(PackError, match="not supported by its cited evidence"):
        validate_generated(output, source)
    prompt = json.loads(diagnostic.prepared_request("pack"))["instructions"]
    assert "does not establish that the API used Python" in prompt
    assert "semantic correctness; the user must review both drafts" in prompt


def test_openai_comparison_uses_existing_adapter_and_same_source():
    from pathlib import Path
    baseline = json.loads((Path(__file__).resolve().parents[2] / "evidence/groq-pack-v2-dry-20260917.json").read_text())["request"]
    wire = json.loads(diagnostic.prepared_request("pack", "openai"))
    assert wire["input"] == baseline["input"]
    assert wire["instructions"] == baseline["instructions"]
    assert wire["model"] == "gpt-5-mini"
    assert wire["max_output_tokens"] == 4000
    assert wire["reasoning"] == {"effort": "minimal"}
    assert wire["text"]["format"]["name"] == "PackProviderOutput"
    assert wire["text"]["format"]["strict"] is True
    plan = evaluation.build_plan("openai", pilot=True, task="pack", pack_reasoning="minimal")
    assert plan["max_requests"] == 1 and plan["max_estimated_cost_usd"] == 0.016
    assert plan["requests"][0]["input_token_estimate"] == len(diagnostic.prepared_request("pack", "openai")) + 2048


def test_minimal_diagnostic_changes_only_reasoning_in_serialized_request():
    from pathlib import Path
    original = json.loads((Path(__file__).resolve().parents[2] /
        "evidence/openai-pack-comparison-dry-20260917.json").read_text())["request"]
    proposed = json.loads(diagnostic.prepared_request("pack", "openai"))
    assert proposed.pop("reasoning") == {"effort": "minimal"}
    assert proposed == original
    assert "pack_reasoning" not in evaluation.build_plan("openai", pilot=True, task="pack")
