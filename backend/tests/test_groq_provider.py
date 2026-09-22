"""Groq contracts use synthetic keys and blocked sockets; never contact Groq."""
import json
from decimal import Decimal, ROUND_CEILING
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
def block_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Network is forbidden in Groq tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.delenv("JOBPILOT_GROQ_TPM", raising=False)
    # Tests must never read the real private .env.
    monkeypatch.setattr(evaluation, "ENV_FILE", tmp_path / "no-private-env.env")


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
        if mode == "incomplete":
            # A length-limited stop that cut the JSON mid-string is a genuine
            # failure; a complete JSON body under "incomplete" is accepted by
            # the provider (covered by test_profile_suggestions.py).
            content["text"] = '{"sug'
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
            assert result.model_dump() == expected.model_dump()
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
    # The v2 pack prompt makes the longer non-pilot fixtures exceed 8,000.
    # Keep the hard gate; full-suite planning is no longer expected to fit.
    with pytest.raises(SystemExit):
        evaluation.main(["--provider", "groq", "--output", str(path)])
    assert not path.exists()
    with pytest.raises(SystemExit):
        evaluation.main(["--provider", "groq", "--live", "--max-cost-usd",
                        "0.24", "--output", str(tmp_path / "live.json")])
    assert not (tmp_path / "live.json").exists()


@pytest.mark.parametrize("enabled,expected_provider", [(True, "openai"), (False, "unknown")])
def test_pack_options_use_independent_openai_config_without_constructing_client(enabled, expected_provider, monkeypatch):
    from app.services import application_pack_service
    monkeypatch.setattr(application_pack_service,
                        "owned_job", lambda *args: None)
    monkeypatch.setattr("openai.OpenAI", lambda **
                        kwargs: pytest.fail("Options constructed a client"))
    scalars = iter([None, "Python required"])
    db = SimpleNamespace(scalar=lambda *args: next(scalars),
                         execute=lambda *args: SimpleNamespace(all=lambda: []))
    config = settings(JOBPILOT_AI_ENABLED=enabled,
                      JOBPILOT_AI_PROVIDER="groq", JOBPILOT_GROQ_API_KEY="synthetic", JOBPILOT_OPENAI_API_KEY="synthetic")
    result = application_pack_service.options(db, "owner", "job", config)
    assert result["provider"] == expected_provider
    assert result["model"] == "gpt-5-mini"
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
    assert plan["max_output_tokens_per_request"] == evaluation.GROQ_MAX_OUTPUT_TOKENS
    assert all(r["max_output_tokens"] == evaluation.GROQ_MAX_OUTPUT_TOKENS
               for r in plan["requests"])
    expected_cost = float(sum(
        (Decimal(r["input_token_estimate"]) * Decimal("0.075") + Decimal(r["max_output_tokens"]) * Decimal("0.30")) / 1_000_000
        for r in plan["requests"]).quantize(Decimal("0.000001"), rounding=ROUND_CEILING))
    assert plan["max_estimated_cost_usd"] == expected_cost
    assert plan["rates_usd_per_million"] == {"input": 0.075, "output": 0.30}
    assert plan["tokens_per_minute"] == evaluation.GROQ_DOCUMENTED_LIMITS["tpm"]
    assert plan["tokens_per_minute_source"] == "documented_assumption"
    assert plan["limits_are_assumptions"] is True
    assert plan["billing_plan_verified"] is False
    assert plan["free_tier_assumed_zero_cost"] is False
    assert "pacing_seconds" not in plan
    assert all(r["complete_token_estimate"] ==
               r["input_token_estimate"] + r["max_output_tokens"]
               for r in plan["requests"])
    assert all(r["complete_token_estimate"] <= plan["tokens_per_minute"]
               for r in plan["requests"])
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
        assert kwargs["max_output_tokens"] == evaluation.GROQ_MAX_OUTPUT_TOKENS
        assert kwargs["service_tier"] == "default"
        index = len(captured_requests) - 1
        case = cases()[0]  # canonical "strong" case
        task = ["profile", "fit", "pack"][index]
        output = evaluation.dispatch(synthetic, task, case["source"])
        return SimpleNamespace(
            status="completed",
            output_parsed=output.model_dump(),
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
    state = {"now": 0.0}

    def advance(seconds):
        slept.append(seconds)
        state["now"] += seconds

    monkeypatch.setattr("time.monotonic", lambda: state["now"])
    monkeypatch.setattr("time.sleep", advance)
    monkeypatch.setattr(openai, "OpenAI", client_factory)
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "groq-secret-key-1234")
    monkeypatch.setattr(evaluation.logging, "disable", lambda *args: None)

    expected_cost = evaluation.build_plan("groq", pilot=True)[
        "max_estimated_cost_usd"]

    report_path = tmp_path / "groq-pilot-run.json"
    exit_code = evaluation.main([
        "--provider", "groq", "--pilot", "--live",
        "--max-cost-usd", str(expected_cost), "--output", str(report_path),
    ])
    assert exit_code == 0
    assert construction_kwargs["base_url"] == "https://api.groq.com/openai/v1"
    assert construction_kwargs["api_key"] == "groq-secret-key-1234"
    assert construction_kwargs["timeout"] == 60
    assert construction_kwargs["max_retries"] == 0

    assert len(captured_requests) == 3
    # Rolling-window scheduling under the 8,000 TPM documented assumption:
    # profile (complete ~7880) dispatches at t=0; fit (~6198) would push the
    # active window over 8000 while profile is still reserved, so it waits for
    # the profile window to expire at t=60; pack (~7584) likewise waits for
    # fit to expire at t=120. Ideal dispatch times 0/60/120.
    assert len(slept) == 2
    assert slept == [pytest.approx(60.0), pytest.approx(60.0)]
    assert state["now"] == pytest.approx(120.0)

    report = json.loads(report_path.read_text())
    assert report["semantic_quality"] == "pending_human_review"
    assert report["attempted_requests"] == 3
    assert len(report["results"]) == 3
    assert all(r["status"] == "contract_pass" for r in report["results"])
    assert report["reserved_cost_usd"] == pytest.approx(expected_cost)
    # 3 requests * (2000 * 0.075 + 500 * 0.30) / 1,000,000 = 3 * (0.15 + 0.15) / 1000 = 0.0009
    assert report["known_usage_cost_usd"] == pytest.approx(0.0009)
    assert "groq-secret-key-1234" not in report_path.read_text()


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_token_scheduler_regression_5311_6198_7584():
    # Fake-clock regression: with instantaneous requests, dispatches happen
    # no earlier than t=0, t=60 and t=120 (each reservation holds the full
    # 60-second window; 5311+6198 would alone exceed the 8000 TPM budget).
    clock = _FakeClock(start=0.0)
    slept = []
    scheduler = evaluation.TokenScheduler(
        8000, clock=clock, sleeper=lambda s: (slept.append(s), clock.advance(s)))
    dispatch_times = []
    for tokens in (5311, 6198, 7584):
        scheduler.reserve(tokens)
        dispatch_times.append(round(clock(), 3))
        # Rolling-window invariant: active reservations never exceed TPM.
        assert scheduler.active_tokens() <= scheduler.capacity
    assert dispatch_times == [0.0, 60.0, 120.0]
    assert len(slept) == 2
    assert all(s == pytest.approx(60.0) for s in slept)
    assert scheduler.active_tokens() == pytest.approx(7584.0)


def test_token_scheduler_waits_until_window_expiry_before_dispatch():
    clock = _FakeClock(start=0.0)
    slept = []
    scheduler = evaluation.TokenScheduler(
        8000, clock=clock, sleeper=lambda s: (slept.append(s), clock.advance(s)))
    scheduler.reserve(5311)  # t=0; active window sum 5311.
    clock.advance(59)        # t=59, still inside the first window.
    assert scheduler.active_tokens() == pytest.approx(5311.0)
    scheduler.reserve(4000)  # 5311+4000 > 8000: block until t=60, then dispatch.
    assert clock() == pytest.approx(60.0)
    assert slept == [pytest.approx(1.0)]
    assert scheduler.active_tokens() <= scheduler.capacity
    assert scheduler.active_tokens() == pytest.approx(4000.0)


def test_capacity_rejects_oversize_single_reservation():
    with pytest.raises(ValueError):
        evaluation.TokenScheduler(8000).reserve(8001)
    with pytest.raises(ValueError):
        evaluation.TokenScheduler(0)


def test_groq_build_plan_rejects_oversize_complete_request(monkeypatch):
    monkeypatch.setenv("JOBPILOT_GROQ_TPM", "500")
    with pytest.raises(ValueError, match="complete input"):
        evaluation.build_plan("groq", pilot=True)


def test_groq_pilot_oversize_rejected_before_client_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic-secret")
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setenv("JOBPILOT_GROQ_TPM", "500")
    monkeypatch.setattr("openai.OpenAI", lambda **
                        kwargs: pytest.fail("Oversize plan constructed a network client"))
    out = tmp_path / "nope.json"
    with pytest.raises(SystemExit) as caught:
        evaluation.main(["--provider", "groq", "--pilot", "--live",
                         "--max-cost-usd", "0.01", "--output", str(out)])
    assert caught.value.code == 2
    assert not out.exists()


def test_groq_accepted_tpm_from_env_file_without_private_env(tmp_path, monkeypatch):
    env_file = tmp_path / "limits.env"
    env_file.write_text('JOBPILOT_GROQ_TPM="12000"\n')
    monkeypatch.setattr(evaluation, "ENV_FILE", env_file)
    path = tmp_path / "plan.json"
    assert evaluation.main(["--provider", "groq", "--pilot",
                            "--output", str(path)]) == 0
    report = json.loads(path.read_text())
    assert report["plan"]["tokens_per_minute"] == 12000
    assert report["plan"]["tokens_per_minute_source"] == "account_from_env"
    assert report["plan"]["limits_are_assumptions"] is False


def test_groq_tokens_per_minute_override_labeling():
    plan = evaluation.build_plan("groq", pilot=True,
                                 env={"JOBPILOT_GROQ_TPM": "12000"})
    assert plan["tokens_per_minute"] == 12000
    assert plan["tokens_per_minute_source"] == "account_from_env"
    assert plan["limits_are_assumptions"] is False
    fallback = evaluation.build_plan("groq", pilot=True,
                                     env={"JOBPILOT_GROQ_TPM": "0"})
    assert fallback["tokens_per_minute"] == evaluation.GROQ_DOCUMENTED_LIMITS["tpm"]
    assert fallback["tokens_per_minute_source"] == "documented_assumption"
    assert fallback["limits_are_assumptions"] is True


def test_groq_execute_reports_incomplete_as_failure_and_stops():
    plan = evaluation.build_plan("groq", pilot=True)

    def parse(**kwargs):
        return SimpleNamespace(
            status="incomplete", output_parsed=None, model="openai/gpt-oss-20b",
            usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                                  output_tokens_details=SimpleNamespace(reasoning_tokens=0)),
        )

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    checkpoints = []
    report = evaluation.execute(client, plan,
                                lambda r: checkpoints.append(json.dumps(r)),
                                scheduler=None, stop_on_failure=True)
    assert report["stopped"] == "Provider failure; pilot stops without retry or fallback"
    assert report["attempted_requests"] == 1
    assert len(report["results"]) == 1
    assert report["results"][0]["status"] == "provider_failure"
    assert report["results"][0]["provider_status"] == "incomplete"


@pytest.mark.parametrize("mode,kind,path", [
    ("json", "json_invalid", []),
    ("type", "string_type", ["suggestions", 0, "HeadlineSuggestion", "value"]),
    ("empty", "string_too_short", ["suggestions", 0, "HeadlineSuggestion", "value"]),
    ("id", "string_pattern_mismatch", ["suggestions", 0, "HeadlineSuggestion", "id"]),
    ("quote", "string_too_long", ["suggestions", 0, "HeadlineSuggestion", "evidence", 0, "quote"]),
    ("count", "too_long", ["suggestions"]),
    ("extra", "extra_forbidden", ["<redacted>"]),
    ("envelope", "float_parsing", ["created_at"]),
])
def test_sdk_validation_report_is_safe_and_stops(tmp_path, mode, kind, path):
    secret = "synthetic-secret-do-not-record"
    suggestion = {"id": "h-1", "field": "headline", "value": "Engineer",
                  "evidence": [{"quote": "Engineer"}]}
    payload = {"suggestions": [suggestion], "partial": False, "message": None}
    if mode == "type":
        suggestion["value"] = {"private": secret}
    elif mode == "empty":
        suggestion["value"] = ""
    elif mode == "id":
        suggestion["id"] = "has spaces " + secret
    elif mode == "quote":
        suggestion["evidence"][0]["quote"] = secret * 100
    elif mode == "count":
        payload["suggestions"] = [suggestion] * 51
    elif mode == "extra":
        payload[secret] = secret
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={
            "id": "resp-test", "object": "response", "created_at": secret if mode == "envelope" else 0,
            "model": "openai/gpt-oss-20b", "status": "completed",
            "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
            "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                      "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}},
            "output": [{"id": "msg-test", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "annotations": [],
                                     "text": '{"' + secret if mode == "json" else json.dumps(payload)}]}],
        })

    report_path = tmp_path / "mock-report.json"
    with OpenAI(api_key=secret, max_retries=0, _strict_response_validation=(mode == "envelope"),
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        report = evaluation.execute(client, evaluation.build_plan("groq", pilot=True),
                                    lambda r: report_path.write_text(json.dumps(r)), stop_on_failure=True)
    assert len(calls) == report["attempted_requests"] == len(report["results"]) == 1
    row = json.loads(report_path.read_text())["results"][0]
    assert row["provider_status"] == ("completed" if mode == "envelope" else "unknown")
    if mode == "envelope":
        assert row["usage"] == {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 0}
    else:
        assert row["usage"] is None  # Content parse errors hide response/usage.
    assert row["status_code"] == (200 if mode == "envelope" else None)
    assert row["validation"]["model"] == ("Response" if mode == "envelope" else "GroqProfileOutput")
    assert any(e["type"] == kind and e["location"] == path for e in row["validation"]["errors"])
    assert secret not in report_path.read_text()
    assert all(set(e) == {"type", "location", "location_truncated"} for e in row["validation"]["errors"])
    assert report["stopped"]


def test_validation_diagnostics_bound_and_redact_untrusted_metadata():
    from app.evaluation.validation_diagnostics import validation_diagnostics
    secret = "synthetic-credential"
    error = ValidationError.from_exception_data(secret, [
        {"type": "extra_forbidden", "loc": ("suggestions", i, secret, *(["value"] * 20)), "input": secret}
        for i in range(30)
    ])
    result = validation_diagnostics(error)["validation"]
    assert result["model"] == "unknown"
    assert result["errors_truncated"] and len(result["errors"]) == 20
    assert all(e["location_truncated"] and len(e["location"]) == 8 for e in result["errors"])
    assert secret not in json.dumps(result)


def test_error_body_tags_cannot_leak_short_credentials():
    from openai import BadRequestError
    response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid"))
    error = BadRequestError("private-message", response=response,
                            body={"error": {"type": "private-key", "code": "private-key"}})
    assert evaluation._safe_error_tags(error) == {"failure_type": "BadRequestError", "status_code": 400,
        "failure_category": "http_rejection", "reason_category": "bad_request"}


@pytest.mark.parametrize("pilot", [True, False])
@pytest.mark.parametrize("task", [None, "profile", "fit", "pack"])
def test_task_selection_precedes_estimation(pilot, task, monkeypatch):
    estimated_tasks = []

    def estimate(selected_task, *args, **kwargs):
        estimated_tasks.append(selected_task)
        assert task is None or selected_task == task
        # This test isolates selection order; budget/SDK checks have dedicated tests.
        return {"sha256": "synthetic", "input_token_estimate": 100,
                "max_output_tokens": kwargs["max_output_tokens"],
                "complete_token_estimate": 100 + kwargs["max_output_tokens"]}

    monkeypatch.setattr(evaluation, "request_plan", estimate)
    plan = evaluation.build_plan("groq", pilot=pilot, task=task)
    count = (1 if pilot else 5) * (3 if task is None else 1)
    assert len(plan["requests"]) == plan["max_requests"] == len(estimated_tasks) == count
    assert {r["task"] for r in plan["requests"]} == (set(evaluation.TASKS) if task is None else {task})
    if pilot:
        assert {r["case"] for r in plan["requests"]} == {"strong"}
        assert plan["max_estimated_cost_usd"] == float(sum(
            (Decimal(r["input_token_estimate"]) * Decimal("0.075") + Decimal(r["max_output_tokens"]) * Decimal("0.30")) / 1_000_000
            for r in plan["requests"]).quantize(Decimal("0.000001"), rounding=ROUND_CEILING))


@pytest.mark.parametrize("mode", ["success", "failure"])
def test_profile_only_cli_dry_and_mocked_live_share_plan(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("JOBPILOT_GROQ_API_KEY", "synthetic-key")
    monkeypatch.setenv("JOBPILOT_EVAL_ALLOW_LIVE", "1")
    monkeypatch.setattr(evaluation.logging, "disable", lambda *args: None)
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: pytest.fail("Dry run constructed client"))
    dry_path = tmp_path / "dry.json"
    args = ["--provider", "groq", "--pilot", "--task", "profile"]
    assert evaluation.main([*args, "--output", str(dry_path)]) == 0
    dry = json.loads(dry_path.read_text())
    assert dry["plan"]["max_requests"] == len(dry["plan"]["requests"]) == 1
    assert [c["id"] for c in dry["cases"]] == ["strong"]
    assert dry["plan"]["tokens_per_minute"] == 8000
    assert dry["plan"]["max_output_tokens_per_request"] == evaluation.GROQ_PROFILE_MAX_OUTPUT_TOKENS
    assert dry["plan"]["retries"] == 0
    calls, reservations = [], []
    reserve = evaluation.TokenScheduler.reserve

    def record_reservation(self, tokens):
        assert self.capacity == 8000
        reservations.append(tokens)
        reserve(self, tokens)

    monkeypatch.setattr(evaluation.TokenScheduler, "reserve", record_reservation)

    def parse(**kwargs):
        calls.append(kwargs)
        assert kwargs["max_output_tokens"] == evaluation.GROQ_PROFILE_MAX_OUTPUT_TOKENS
        assert kwargs["text_format"].__name__ == "GroqProfileOutput"
        if mode == "failure":
            kwargs["text_format"].model_validate_json('{')
        return SimpleNamespace(status="completed", usage=None, model="synthetic",
                               output_parsed=DeterministicTestProvider().suggest(cases()[0]["source"]["cv_text"]).model_dump())

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.responses = SimpleNamespace(parse=parse)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("openai.OpenAI", Client)
    live_path = tmp_path / "mocked-live.json"
    assert evaluation.main([*args, "--live", "--max-cost-usd",
                            str(dry["plan"]["max_estimated_cost_usd"]),
                            "--output", str(live_path)]) == (0 if mode == "success" else 1)
    live = json.loads(live_path.read_text())
    assert live["plan"] == dry["plan"]
    assert live["attempted_requests"] == len(calls) == len(live["results"]) == 1
    assert reservations == [dry["plan"]["requests"][0]["complete_token_estimate"]]
    if mode == "failure":
        assert live["stopped"]
        assert live["results"][0]["validation"]["errors"][0]["type"] == "json_invalid"


@pytest.mark.parametrize("nested", [True, False])
def test_http_rejection_retains_only_allowlisted_details(nested):
    from openai import BadRequestError
    detail = {"type": "invalid_request_error", "code": "json_validate_failed",
              "message": "private-secret", "failed_generation": "private-body"}
    error = BadRequestError("private-secret", response=httpx.Response(
        400, request=httpx.Request("POST", "https://example.invalid")),
        body={"error": detail} if nested else detail)
    tags = evaluation._safe_error_tags(error)
    assert tags == {"failure_type": "BadRequestError", "status_code": 400,
                   "failure_category": "http_rejection", "reason_category": "bad_request",
                   "provider_error_type": "invalid_request_error",
                   "provider_error_code": "json_validate_failed"}
    assert "private" not in json.dumps(tags)


def test_profile_budget_rounds_0009195_upward(monkeypatch):
    assert evaluation.maximum_budget(Decimal("0.0009195")) == 0.000920
    assert evaluation.maximum_budget(Decimal("0.000920")) == 0.000920
    monkeypatch.setattr(evaluation, "request_plan", lambda *args, **kwargs: {
        "input_token_estimate": 6260, "max_output_tokens": 1500,
        "complete_token_estimate": 7760, "sha256": "synthetic"})
    plan = evaluation.build_plan("groq", pilot=True, task="profile")
    reported = Decimal(str(plan["max_estimated_cost_usd"]))
    calculated = (Decimal(6260) * Decimal("0.075") + Decimal(1500) * Decimal("0.30")) / Decimal(1000000)
    assert calculated == Decimal("0.0009195")
    assert reported == Decimal("0.000920")
    assert reported >= calculated


def test_retained_http_code_does_not_prove_request_schema_rejection():
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {
            "type": "invalid_request_error", "code": "json_validate_failed",
            "message": "private provider explanation", "failed_generation": "private output"}})

    with OpenAI(api_key="synthetic", base_url="https://api.groq.com/openai/v1", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(transport))) as client:
        report = evaluation.execute(client, evaluation.build_plan("groq", pilot=True, task="profile"),
                                    lambda report: None, stop_on_failure=True)
    assert len(calls) == report["attempted_requests"] == 1
    row = report["results"][0]
    assert row["failure_category"] == "http_rejection"  # Transport outcome only.
    assert row["provider_error_code"] == "json_validate_failed"
    assert row["status_code"] == 400
    assert row["output"] is None and row["usage"] is None
    assert "validation" not in row  # No client content parse occurred.
    assert "private" not in json.dumps(report)
    assert report["stopped"]
