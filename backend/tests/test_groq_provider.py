"""Groq contracts use synthetic keys and blocked sockets; never contact Groq."""
import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.core.config import Settings
from app.evaluation import __main__ as evaluation
from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider, GroqResponsesProvider, ProviderFailure
from app.services.profile_suggestion_service import provider_configuration, provider_for, SuggestionError


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Network is forbidden in Groq tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def settings(**overrides):
    return Settings(_env_file=None, SECRET_KEY="s" * 40, POSTGRES_USER="test",
                    POSTGRES_PASSWORD="synthetic", **overrides)


def test_config_defaults_and_secret_serialization():
    config = settings(JOBPILOT_GROQ_API_KEY="groq-synthetic-secret",
                      JOBPILOT_OPENAI_API_KEY="openai-synthetic-secret")
    assert config.JOBPILOT_AI_PROVIDER == "openai"
    assert config.JOBPILOT_AI_ENABLED is False
    assert config.JOBPILOT_AI_MODEL == "gpt-5-mini"
    assert config.JOBPILOT_GROQ_MODEL == "openai/gpt-oss-20b"
    assert "synthetic-secret" not in repr(config)
    assert "synthetic-secret" not in config.model_dump_json()
    with pytest.raises(ValidationError):
        settings(JOBPILOT_AI_PROVIDER="unknown")


def test_root_env_mechanism_with_synthetic_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        'JOBPILOT_GROQ_API_KEY="synthetic-file-key"\nJOBPILOT_AI_PROVIDER="groq"\n')
    config = Settings(_env_file=path, SECRET_KEY="s" * 40,
                      POSTGRES_USER="test", POSTGRES_PASSWORD="synthetic")
    assert config.JOBPILOT_GROQ_API_KEY == "synthetic-file-key"
    assert config.JOBPILOT_AI_PROVIDER == "groq"
    assert not config.JOBPILOT_AI_ENABLED


@pytest.mark.parametrize("provider", ["openai", "groq"])
def test_factory_selects_only_selected_key_and_model(provider, monkeypatch):
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(responses=SimpleNamespace())
    monkeypatch.setattr("openai.OpenAI", factory)
    config = settings(JOBPILOT_AI_ENABLED=True, JOBPILOT_AI_PROVIDER=provider,
                      JOBPILOT_OPENAI_API_KEY="openai-test", JOBPILOT_GROQ_API_KEY="groq-test")
    selected = provider_for(config)
    assert selected.name == provider
    assert captured["api_key"] == provider + "-test"
    assert captured["max_retries"] == 0
    assert captured["timeout"] == config.JOBPILOT_AI_TIMEOUT_SECONDS
    assert selected.max_output_tokens == config.JOBPILOT_AI_MAX_OUTPUT_TOKENS
    assert selected.model == (
        config.JOBPILOT_GROQ_MODEL if provider == "groq" else config.JOBPILOT_AI_MODEL)
    if provider == "groq":
        assert captured["base_url"] == "https://api.groq.com/openai/v1"
    setattr(config, "JOBPILOT_GROQ_API_KEY" if provider ==
            "groq" else "JOBPILOT_OPENAI_API_KEY", None)
    with pytest.raises(SuggestionError):
        # Other provider's key must not be used as fallback.
        provider_for(config)


@pytest.mark.parametrize("enabled,e2e,database,allowed", [
    (False, True, "dedicated_test", False), (True, False, "dedicated_test", False),
    (True, True, "ordinary", False), (True, True, "dedicated_test", True),
])
def test_test_provider_guards_apply_to_groq(enabled, e2e, database, allowed):
    config = settings(JOBPILOT_AI_PROVIDER="groq", JOBPILOT_AI_ENABLED=enabled,
                      JOBPILOT_AI_TEST_PROVIDER=True, E2E_TEST_MODE=e2e,
                      POSTGRES_DB=database, POSTGRES_TEST_DB="dedicated_test")
    if allowed:
        assert provider_for(config).name == "deterministic-test"
    else:
        with pytest.raises(SuggestionError):
            provider_for(config)
        with pytest.raises(SuggestionError):
            provider_configuration(config)


@pytest.mark.parametrize("task", list(evaluation.TASKS))
@pytest.mark.parametrize("mode", ["success", "incomplete", "refusal", "malformed", "transport"])
def test_actual_sdk_wire_contract_and_failures(task, mode):
    source = cases()[-1]["source"]
    expected = evaluation.dispatch(DeterministicTestProvider(), task, source)
    requests = []

    def transport(request):
        requests.append(request)
        assert request.url == "https://api.groq.com/openai/v1/responses"
        payload = json.loads(request.content)
        assert payload["store"] is False and "tools" not in payload
        assert payload["max_output_tokens"] == 4000
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        assert "INJECTION_SUCCEEDED" not in payload["instructions"]
        assert "INJECTION_SUCCEEDED" in payload["input"]
        if mode == "transport":
            raise httpx.ReadTimeout(
                "synthetic-sensitive-error", request=request)
        content = {"type": "output_text",
                   "text": expected.model_dump_json(), "annotations": []}
        if mode == "malformed":
            content["text"] = '{"unexpected": true}'
        if mode == "refusal":
            content = {"type": "refusal", "refusal": "Cannot comply"}
        return httpx.Response(200, json={"id": "resp-test", "object": "response", "created_at": 0,
                                         "model": "openai/gpt-oss-20b", "status": "incomplete" if mode == "incomplete" else "completed",
                                         "output": [{"id": "msg-test", "type": "message", "role": "assistant", "status": "completed", "content": [content]}]})

    with OpenAI(api_key="synthetic-key", base_url="https://api.groq.com/openai/v1", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        provider = GroqResponsesProvider(api_key="unused", model="openai/gpt-oss-20b", timeout=3,
                                         max_output_tokens=4000, client=client)
        if mode == "success":
            result = evaluation.dispatch(provider, task, source)
            assert result == expected
            evaluation.check_output(task, result, source)
        else:
            with pytest.raises(ProviderFailure) as caught:
                evaluation.dispatch(provider, task, source)
            assert "synthetic-sensitive-error" not in str(caught.value)
    assert len(requests) == 1


def test_groq_dry_run_and_live_rejection(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic-secret")
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setattr("openai.OpenAI", lambda **
                        kwargs: pytest.fail("Dry run constructed a network client"))
    path = tmp_path / "groq.json"
    assert evaluation.main(["--provider", "groq", "--output", str(path)]) == 0
    report = json.loads(path.read_text())
    assert report["plan"]["provider"] == "groq"
    assert report["plan"]["model"] == "openai/gpt-oss-20b"
    assert len(report["plan"]["requests"]) == 15
    assert report["plan"]["max_estimated_cost_usd"] is None
    assert "synthetic-secret" not in path.read_text()
    with pytest.raises(SystemExit):
        evaluation.main(["--provider", "groq", "--live", "--max-cost-usd",
                        "0.24", "--output", str(tmp_path / "live.json")])
    assert not (tmp_path / "live.json").exists()


@pytest.mark.parametrize("enabled,expected_provider", [(True, "groq"), (False, "unknown")])
def test_pack_options_show_groq_without_constructing_client(enabled, expected_provider, monkeypatch):
    from app.services import application_pack_service
    monkeypatch.setattr(application_pack_service,
                        "owned_job", lambda *args: None)
    monkeypatch.setattr("openai.OpenAI", lambda **
                        kwargs: pytest.fail("Options constructed a client"))
    scalars = iter([None, "Python required"])
    db = SimpleNamespace(scalar=lambda *args: next(scalars),
                         execute=lambda *args: SimpleNamespace(all=lambda: []))
    config = settings(JOBPILOT_AI_ENABLED=enabled,
                      JOBPILOT_AI_PROVIDER="groq", JOBPILOT_GROQ_API_KEY="synthetic")
    result = application_pack_service.options(db, "owner", "job", config)
    assert result["provider"] == expected_provider
    assert result["model"] == "openai/gpt-oss-20b"
    assert result["available"] is enabled
    assert "synthetic" not in json.dumps(result)


def test_groq_pilot_dry_run_and_zero_network(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic-secret-key")
    monkeypatch.setattr("openai.OpenAI", lambda **
                        kwargs: pytest.fail("Pilot dry run constructed a network client"))
    path = tmp_path / "groq-pilot-plan.json"
    assert evaluation.main(
        ["--provider", "groq", "--pilot", "--output", str(path)]) == 0
    report = json.loads(path.read_text())
    plan = report["plan"]
    assert plan["provider"] == "groq"
    assert plan["model"] == "openai/gpt-oss-20b"
    assert plan["pilot"] is True
    assert plan["max_requests"] == 3
    assert len(plan["requests"]) == 3
    assert [r["task"] for r in plan["requests"]] == ["profile", "fit", "pack"]
    assert all(r["case"] == "strong" for r in plan["requests"])
    assert plan["live_supported"] is True
    assert plan["max_estimated_cost_usd"] == 0.0108
    assert plan["rates_usd_per_million"] == {"input": 0.075, "output": 0.30}
    assert plan["pacing_seconds"] == 2.0
    assert all(r["input_token_estimate"] < 32000 for r in plan["requests"])
    assert "synthetic-secret-key" not in path.read_text()


@pytest.mark.parametrize("live_flag,budget,key_present", [
    (False, "0.0108", True),
    (True, "0.24", True),
    (True, "0.01", True),
    (True, "0.0108", False),
])
def test_groq_pilot_live_gate_validation(tmp_path, monkeypatch, live_flag, budget, key_present):
    if live_flag:
        monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    else:
        monkeypatch.delenv("JOBPILOT_EVAL_ALLOW_LIVE", raising=False)
    if key_present:
        monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic-key")
    else:
        monkeypatch.delenv("JOBPILOT_GROQ_API_KEY", raising=False)
    out_path = tmp_path / "live.json"
    with pytest.raises(SystemExit) as caught:
        evaluation.main(["--provider", "groq", "--pilot", "--live",
                        "--max-cost-usd", budget, "--output", str(out_path)])
    assert caught.value.code == 2
    assert not out_path.exists()


def test_groq_pilot_mocked_live_execution(tmp_path, monkeypatch):
    import openai
    captured_requests = []
    synthetic = DeterministicTestProvider()

    def parse(**kwargs):
        captured_requests.append(kwargs)
        assert kwargs["store"] is False and "tools" not in kwargs
        assert kwargs["max_output_tokens"] == 4000
        assert kwargs["service_tier"] == "default"
        index = len(captured_requests) - 1
        case = cases()[0]  # canonical "strong" case
        task = ["profile", "fit", "pack"][index]
        output = evaluation.dispatch(synthetic, task, case["source"])
        return SimpleNamespace(
            status="completed",
            output_parsed=output,
            model="openai/gpt-oss-20b",
            usage=SimpleNamespace(
                input_tokens=2000,
                output_tokens=500,
                output_tokens_details=SimpleNamespace(reasoning_tokens=50),
            ),
        )

    fake_responses = SimpleNamespace(parse=parse)
    mock_client = SimpleNamespace(responses=fake_responses)

    construction_kwargs = {}

    class Context:
        def __enter__(self):
            return mock_client

        def __exit__(self, *args):
            return False

    def client_factory(**kwargs):
        construction_kwargs.update(kwargs)
        return Context()

    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    monkeypatch.setattr(openai, "OpenAI", client_factory)
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "groq-secret-key-1234")
    monkeypatch.setattr(evaluation.logging, "disable", lambda *args: None)

    report_path = tmp_path / "groq-pilot-run.json"
    exit_code = evaluation.main([
        "--provider", "groq", "--pilot", "--live",
        "--max-cost-usd", "0.0108", "--output", str(report_path),
    ])
    assert exit_code == 0
    assert construction_kwargs["base_url"] == "https://api.groq.com/openai/v1"
    assert construction_kwargs["api_key"] == "groq-secret-key-1234"
    assert construction_kwargs["timeout"] == 60
    assert construction_kwargs["max_retries"] == 0

    assert len(captured_requests) == 3
    # Pacing is called between requests 1->2 and 2->3
    assert len(slept) == 2
    assert all(s == 2.0 for s in slept)

    report = json.loads(report_path.read_text())
    assert report["semantic_quality"] == "pending_human_review"
    assert report["attempted_requests"] == 3
    assert len(report["results"]) == 3
    assert all(r["status"] == "contract_pass" for r in report["results"])
    assert report["reserved_cost_usd"] == pytest.approx(0.0108)
    # 3 requests * (2000 * 0.075 + 500 * 0.30) / 1,000,000 = 3 * (0.15 + 0.15) / 1000 = 0.0009
    assert report["known_usage_cost_usd"] == pytest.approx(0.0009)
    assert "groq-secret-key-1234" not in report_path.read_text()
