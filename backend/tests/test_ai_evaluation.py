"""Evaluation preparation tests: all network access is forbidden."""
import json
import socket
from types import SimpleNamespace

import pytest

from app.evaluation import __main__ as evaluation
from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Evaluation tests must never open a network connection")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.delenv("JOBPILOT_EVAL_ALLOW_LIVE", raising=False)
    monkeypatch.delenv("JOBPILOT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("JOBPILOT_GROQ_API_KEY", raising=False)
    # Tests must never read the real private .env.
    monkeypatch.setattr(evaluation, "ENV_FILE", tmp_path / "no-private-env.env")


def test_default_is_offline_even_with_credentials_and_application_flags(tmp_path, monkeypatch):
    import openai
    monkeypatch.setenv("JOBPILOT_OPENAI_API_KEY", "secret-test-value")
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_AI_ENABLED", "true")
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: pytest.fail("Client constructed in dry run"))
    path = tmp_path / "plan.json"
    assert evaluation.main(["--output", str(path)]) == 0
    report = json.loads(path.read_text())
    assert report["mode"] == "planned"
    assert len(report["plan"]["requests"]) == 15
    assert "secret-test-value" not in path.read_text()
    assert "results" not in report


@pytest.mark.parametrize("flag,budget,key", [(False, "0.24", True), (True, "0.23", True),
                                                (True, "nan", True), (True, "0.24", False)])
def test_live_requires_all_gates(tmp_path, monkeypatch, flag, budget, key):
    if flag:
        monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    if key:
        monkeypatch.setenv("JOBPILOT_OPENAI_API_KEY", "synthetic")
    else:
        monkeypatch.delenv("JOBPILOT_OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as caught:
        evaluation.main(["--live", "--max-cost-usd", budget, "--output", str(tmp_path / "run.json")])
    assert caught.value.code == 2
    assert not (tmp_path / "run.json").exists()


def test_existing_evidence_is_not_overwritten(tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("preserve me")
    with pytest.raises(SystemExit):
        evaluation.main(["--output", str(path)])
    assert path.read_text() == "preserve me"


def test_all_requests_bounded_and_source_instructions_stay_data():
    plan = evaluation.build_plan()
    assert len({(r["case"], r["task"]) for r in plan["requests"]}) == 15
    assert all(r["input_token_estimate"] < 32000 for r in plan["requests"])
    assert evaluation.MAX_REQUESTS * (32000 * .25 + 4000 * 2) / 1_000_000 == .24
    source = cases()[-1]["source"]
    for task in evaluation.TASKS:
        assert evaluation.request_plan(task, source)
    source["cv_text"] = "x" * 32000
    with pytest.raises(ValueError, match="input allowance"):
        evaluation.request_plan("profile", source)


@pytest.mark.parametrize("task", list(evaluation.TASKS))
def test_invalid_evidence_fails_evaluation(task):
    source = cases()[0]["source"]
    output = evaluation.dispatch(DeterministicTestProvider(), task, source)
    if task == "profile":
        output.suggestions[0].evidence[0].quote = "fabricated source passage"
    elif task == "fit":
        output.requirements[0].candidate_fact_ids = ["fact-999"]
    else:
        output.cv.blocks[1].evidence[0].cv_quote = "fabricated source passage"
    with pytest.raises(Exception):
        evaluation.check_output(task, output, source)


def fake_client(mode="success"):
    captured = []
    synthetic = DeterministicTestProvider()

    def parse(**kwargs):
        captured.append(kwargs)
        assert kwargs["store"] is False and "tools" not in kwargs
        assert kwargs["max_output_tokens"] == 4000
        assert kwargs["service_tier"] == "default"
        if mode == "exception":
            raise RuntimeError("secret-test-value")
        index = len(captured) - 1
        case = cases()[index // 3]
        task = list(evaluation.TASKS)[index % 3]
        output = evaluation.dispatch(synthetic, task, case["source"])
        if mode == "invalid_evidence" and task == "profile":
            output.suggestions[0].evidence[0].quote = "not in CV"
        return SimpleNamespace(status="incomplete" if mode == "incomplete" else "completed",
            output_parsed=None if mode == "refusal" else ({} if mode == "malformed" else output),
            model="resolved-synthetic-model",
            usage=None if mode == "unknown_usage" else SimpleNamespace(
                input_tokens=32001 if mode == "over_limit" else 100,
                output_tokens=50, output_tokens_details=SimpleNamespace(reasoning_tokens=10)))
    return SimpleNamespace(responses=SimpleNamespace(parse=parse)), captured


@pytest.mark.parametrize("mode", ["success", "exception", "incomplete", "refusal", "malformed", "unknown_usage", "invalid_evidence", "over_limit"])
def test_reports_failures_usage_and_checkpoints_without_secret_leaks(mode):
    client, captured = fake_client(mode)
    checkpoints = []
    report = evaluation.execute(client, evaluation.build_plan(), lambda r: checkpoints.append(json.dumps(r)))
    count = 1 if mode == "over_limit" else 15
    assert report["attempted_requests"] == len(captured) == count
    assert len(checkpoints) >= count + 1
    assert "secret-test-value" not in json.dumps(report)
    assert report["semantic_quality"] == "pending_human_review"
    assert all(row["latency_seconds"] >= 0 for row in report["results"])
    if mode in {"exception", "incomplete", "refusal", "malformed"}:
        assert all(row["status"] == "provider_failure" for row in report["results"])
    if mode in {"unknown_usage", "exception"}:
        assert report["unknown_usage_requests"] == 15
        assert report["reserved_cost_usd"] == .24
        assert all(row["estimated_cost_usd"] is None for row in report["results"])
    if mode == "success":
        assert all(row["status"] == "contract_pass" for row in report["results"])
        assert report["known_usage_cost_usd"] == pytest.approx(.001875)
    if mode == "invalid_evidence":
        assert sum(row["status"] == "validation_failure" for row in report["results"]) == 5
    if mode == "over_limit":
        assert report["stopped"]


def test_live_client_is_bounded_and_report_written_with_mock_only(tmp_path, monkeypatch):
    import openai
    client, captured = fake_client()
    construction = {}

    class Context:
        def __enter__(self):
            return client

        def __exit__(self, *args):
            return False

    def factory(**kwargs):
        construction.update(kwargs)
        return Context()

    monkeypatch.setattr(openai, "OpenAI", factory)
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(evaluation.logging, "disable", lambda *args: None)
    path = tmp_path / "mock.json"
    assert evaluation.main(["--live", "--max-cost-usd", "0.24", "--output", str(path)]) == 0
    assert construction["max_retries"] == 0
    assert construction["timeout"] == 60
    assert construction["base_url"] == "https://api.openai.com/v1"
    assert len(captured) == 15
    assert json.loads(path.read_text())["semantic_quality"] == "pending_human_review"
