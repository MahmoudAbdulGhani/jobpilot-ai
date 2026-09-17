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
    assert payload["max_output_tokens"] == 1500
    assert "reasoning" not in payload
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["name"] == "PackProviderOutput"
    plan = evaluation.build_plan("groq", pilot=True, task="pack")
    assert plan["max_requests"] == 1 and plan["retries"] == 0
    assert plan["requests"][0]["input_token_estimate"] == len(diagnostic.prepared_request("pack")) + 2048
    assert plan["requests"][0]["complete_token_estimate"] <= 8000

@pytest.mark.parametrize("mode", ["success", "missing_notes", "missing_nullable", "missing_letter", "truncated", "incomplete", "empty_evidence", "unsupported_quote", "http_schema", "http_generation"])
def test_pack_diagnostic_acceptance_and_safe_capture(tmp_path, monkeypatch, mode):
    dry, result = tmp_path / "dry.json", tmp_path / "result.json"
    diagnostic.main(["--task", "pack", "--output", str(dry)])
    plan = json.loads(dry.read_text())["plan"]
    output = DeterministicTestProvider().create_pack(cases()[0]["source"]).model_dump(mode="json")
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
        if mode.startswith("http_"):
            return httpx.Response(400, json={"error": {"type": "invalid_request_error",
                "code": "invalid_json_schema" if mode == "http_schema" else "json_validate_failed",
                "message": "schema invalid private-token secret@example.test",
                "failed_generation": generation[:-10] if mode == "http_generation" else None}})
        return httpx.Response(200, json={"id": "mock", "object": "response", "created_at": 0,
            "model": "openai/gpt-oss-20b", "status": "incomplete" if mode == "incomplete" else "completed",
            "output": [{"id": "msg", "type": "message", "role": "assistant", "status": "completed", "content": [
                {"type": "output_text", "text": generation, "annotations": []}]}]})
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic")
    monkeypatch.setattr(diagnostic.logging, "disable", lambda *args: None)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    code = diagnostic.main(["--task", "pack", "--live", "--max-cost-usd", str(plan["max_estimated_cost_usd"]), "--dry-report", str(dry), "--output", str(result)])
    report = json.loads(result.read_text())
    assert len(calls) == report["actual_request_count"] == 1
    assert (code == 0) == (mode == "success")
    assert (report["results"][0]["status"] == "contract_pass") == (mode == "success")
    assert "private-token" not in result.read_text() and "secret@example.test" not in result.read_text()
    if mode in ("missing_notes", "missing_nullable"):
        assert report["synthetic_diagnostic"]["returned_generation_local_parse"] == "failed"
    if mode == "http_generation":
        assert report["synthetic_diagnostic"]["failed_generation_local_parse"] == "failed"
