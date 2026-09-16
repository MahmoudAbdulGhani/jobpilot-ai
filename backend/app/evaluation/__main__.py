"""Run with --help. Default is an offline request plan, even with credentials set."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from types import SimpleNamespace

from dotenv import dotenv_values

from app.evaluation.fixtures import cases
from app.evaluation.validation_diagnostics import validation_diagnostics
from app.schemas.job_fit import CandidateFact
from app.services.ai_provider import (
    OpenAIResponsesProvider, GroqResponsesProvider, ProviderFailure, PROMPT_VERSION,
    JOB_FIT_PROMPT_VERSION, PACK_PROMPT_VERSION,
)
from app.services.profile_suggestion_service import validate_output as validate_suggestions
from app.services.job_fit_service import validate_output as validate_fit
from app.services.application_pack_service import validate_generated

MODEL = "gpt-5-mini"
GROQ_MODEL = "openai/gpt-oss-20b"
MAX_REQUESTS = 15
PILOT_REQUESTS = 3
MAX_INPUT_TOKENS_ESTIMATE = 32_000
MAX_OUTPUT_TOKENS = 4_000
TIMEOUT = 60
INPUT_USD_PER_MILLION = 0.25
OUTPUT_USD_PER_MILLION = 2.0
PER_REQUEST_USD = 0.016
MAX_COST_USD = 0.24

# Assumed Groq rate limits for openai/gpt-oss-20b. The published developer
# figure is ~8,000 TPM; the pilot assumes that documented value unless the
# account's actual limits (or retained provider headers) prove otherwise.
# The scheduler GATE uses this ceiling, so every planned request must fit:
# the profile wire schema is kept budget-sized by omitting metadata and some
# constraints that local parsing still enforces (and can therefore reject),
# never by inflating the assumed limit or shrinking the estimate. A higher
# account tier can be supplied through JOBPILOT_GROQ_TPM in the gitignored
# .env or environment.
GROQ_DOCUMENTED_LIMITS = {
    "rpm": 30, "rpd": 1_000, "tpm": 8_000, "tpd": 200_000,
}
GROQ_TPM_ENV = "JOBPILOT_GROQ_TPM"
GROQ_MAX_OUTPUT_TOKENS = 1_500
# Reservation rates are Developer-tier documented pricing assumptions used
# only to bound the pilot cost acknowledgment. The free tier does not imply
# a zero-cost guarantee; the account's billing plan is not verified.
GROQ_INPUT_USD_PER_MILLION = 0.075
GROQ_OUTPUT_USD_PER_MILLION = 0.30

TASKS = {"profile": PROMPT_VERSION,
         "fit": JOB_FIT_PROMPT_VERSION, "pack": PACK_PROMPT_VERSION}

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


def groq_tokens_per_minute(env=None):
    env = env or {}
    raw = os.environ.get(GROQ_TPM_ENV) or env.get(GROQ_TPM_ENV)
    if raw:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value, "account_from_env"
    return GROQ_DOCUMENTED_LIMITS["tpm"], "documented_assumption"


def _load_dotenv(path=None):
    path = Path(path) if path is not None else ENV_FILE
    if not path.exists():
        return {}
    return dict(dotenv_values(path))


def dispatch(provider, task, source):
    if task == "profile":
        return provider.suggest(source["cv_text"])
    if task == "fit":
        return provider.analyze(source["job"]["description"],
                                [CandidateFact.model_validate(f) for f in source["profile_facts"]])
    return provider.create_pack(source)


class Planned(ProviderFailure):
    pass


def request_plan(task, source, provider_name="openai", max_output_tokens=None,
                 max_total_tokens=None):
    if max_output_tokens is None:
        max_output_tokens = MAX_OUTPUT_TOKENS
    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        raise Planned()

    provider_class = GroqResponsesProvider if provider_name == "groq" else OpenAIResponsesProvider
    provider = provider_class(
        api_key="offline-placeholder", model=GROQ_MODEL if provider_name == "groq" else MODEL, timeout=TIMEOUT,
        max_output_tokens=max_output_tokens,
        client=SimpleNamespace(responses=SimpleNamespace(parse=capture)),
    )
    try:
        dispatch(provider, task, source)
    except Planned:
        pass
    # Include schema/instructions, not just source text. UTF-8 byte count is a
    # deliberately conservative token estimate, plus protocol/schema allowance.
    serializable = {**captured,
                    "text_format": captured["text_format"].model_json_schema()}
    encoded = json.dumps(serializable, ensure_ascii=True,
                         sort_keys=True).encode()
    estimate = len(encoded) + 2048
    if estimate > MAX_INPUT_TOKENS_ESTIMATE:
        raise ValueError("Request exceeds the evaluation input allowance")
    complete = estimate + max_output_tokens
    if max_total_tokens is not None and complete > max_total_tokens:
        raise ValueError(
            "Request exceeds the complete input+output token allowance")
    if captured.get("store") is not False or "tools" in captured:
        raise ValueError("Evaluation requires tool-free, nonstored requests")
    return {"sha256": hashlib.sha256(encoded).hexdigest(),
            "input_token_estimate": estimate,
            "max_output_tokens": max_output_tokens,
            "complete_token_estimate": complete}


def build_plan(provider_name="openai", pilot=False, env=None):
    if provider_name not in {"openai", "groq"}:
        raise ValueError("Unsupported evaluation provider")
    env = env or {}
    all_cases = cases()
    selected_cases = all_cases[:1] if pilot else all_cases
    expected_requests = PILOT_REQUESTS if pilot else MAX_REQUESTS
    groq = provider_name == "groq"
    output_cap = GROQ_MAX_OUTPUT_TOKENS if groq else MAX_OUTPUT_TOKENS
    tokens_per_minute = None
    rate_limit_source = None
    if groq:
        tokens_per_minute, rate_limit_source = groq_tokens_per_minute(env)
    entries = []
    for case in selected_cases:
        for task, version in TASKS.items():
            entries.append({"case": case["id"], "task": task, "prompt_version": version,
                            **request_plan(task, case["source"], provider_name,
                                           max_output_tokens=output_cap,
                                           max_total_tokens=tokens_per_minute)})
    if len(entries) != expected_requests:
        raise ValueError(
            "Fixture count changed; review the request and cost budget")

    if groq:
        live_supported = bool(pilot)
        rates = {"input": GROQ_INPUT_USD_PER_MILLION,
                 "output": GROQ_OUTPUT_USD_PER_MILLION} if pilot else None
        max_cost = (
            round(sum(
                (e["input_token_estimate"] * GROQ_INPUT_USD_PER_MILLION +
                 e["max_output_tokens"] * GROQ_OUTPUT_USD_PER_MILLION) / 1_000_000
                for e in entries), 6) if pilot else None
        )
    else:
        live_supported = True
        rates = {"input": INPUT_USD_PER_MILLION,
                 "output": OUTPUT_USD_PER_MILLION}
        max_cost = round(len(entries) * PER_REQUEST_USD, 4)

    plan = {
        "provider": provider_name,
        "model": GROQ_MODEL if provider_name == "groq" else MODEL,
        "pilot": pilot,
        "max_requests": expected_requests,
        "max_input_tokens_estimate_per_request": MAX_INPUT_TOKENS_ESTIMATE,
        "max_output_tokens_per_request": output_cap,
        "timeout_seconds": TIMEOUT,
        "retries": 0,
        "live_supported": live_supported,
        "max_estimated_cost_usd": max_cost,
        "rates_usd_per_million": rates,
        "requests": entries,
    }

    if groq:
        plan["tokens_per_minute"] = tokens_per_minute
        plan["tokens_per_minute_source"] = rate_limit_source
        plan["rate_limit_documented"] = dict(GROQ_DOCUMENTED_LIMITS)
        plan["limits_are_assumptions"] = rate_limit_source == "documented_assumption"
        plan["billing_plan_verified"] = False
        plan["free_tier_assumed_zero_cost"] = False
        plan["pricing_note"] = (
            "Groq free and paid Developer tiers have different rate limits "
            "and pricing; reservation rates are Developer-tier documented "
            "assumptions, not proof of this account's billing plan or a "
            "guarantee of zero cost."
        )

    return plan


def check_output(task, output, source):
    if task == "profile":
        accepted, partial = validate_suggestions(output, source["cv_text"])
        if len(accepted) != len(output.suggestions):
            raise ValueError("Suggestions rejected by production validator")
        return {"partial": partial, "empty": not accepted}
    if task == "fit":
        validate_fit(output, source["job"]["description"],
                     [CandidateFact.model_validate(f) for f in source["profile_facts"]])
        return {"empty": not output.requirements}
    validate_generated(output, source)
    return {}


def _safe_error_tags(error):
    """Bound, type-checked failure metadata; never messages or payloads.

    Retain numeric status and allowlisted validation metadata. Provider body
    type/code strings are untrusted too: even short strings can be credentials.
    """
    tags = {"failure_type": type(error).__name__}
    status_code = getattr(error, "status_code", None)
    if not isinstance(status_code, int):
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(status_code, int):
        tags["status_code"] = status_code
    # Envelope validation errors expose the received body. Retain only known
    # status enums and checked token counts; never copy the body itself.
    from openai import APIResponseValidationError
    if isinstance(error, APIResponseValidationError) and isinstance(error.body, dict):
        status = error.body.get("status")
        if isinstance(status, str) and status in {
            "completed", "failed", "in_progress", "cancelled", "queued", "incomplete",
        }:
            tags["provider_status"] = status
        usage = error.body.get("usage")
        if isinstance(usage, dict) and all(
            type(usage.get(key)) is int and 0 <= usage[key] <= 10**12
            for key in ("input_tokens", "output_tokens")
        ):
            details = usage.get("output_tokens_details")
            reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
            tags["usage"] = {
                "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                "reasoning_tokens": reasoning if type(reasoning) is int and 0 <= reasoning <= 10**12 else None,
            }
    tags.update(validation_diagnostics(error))
    return tags


class Meter:
    """Observe usage without changing the production adapter or printing errors."""

    def __init__(self, client, max_requests=MAX_REQUESTS):
        self.client = client
        self.responses = self
        self.calls = 0
        self.max_requests = max_requests
        self.last = {}

    def parse(self, **kwargs):
        if self.calls >= self.max_requests:
            raise ProviderFailure("Evaluation request budget exhausted")
        self.calls += 1  # Failures consume the allowance too; never retry.
        self.last = {
            "provider_status": "unknown", "status_code": None, "usage": None}
        try:
            response = self.client.responses.parse(
                **kwargs, service_tier="default")
        except Exception as error:
            # Record only bounded, typed tags (exception class, numeric status
            # code, allowlisted validation metadata); never messages or payloads,
            # which may include credentials or the request body.
            self.last.update(_safe_error_tags(error))
            raise
        usage = getattr(response, "usage", None)
        self.last = {"provider_status": getattr(response, "status", "unknown"),
                     "status_code": None,
                     "returned_model": getattr(response, "model", None), "usage": None}
        if usage is not None:
            self.last["usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                                  "reasoning_tokens": getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", None)}
        return response


class TokenScheduler:
    """Rolling-60-second token-budget scheduler with timestamped reservations.

    Each reservation keeps its full estimated input+maximum-output tokens for
    a 60-second window. Before dispatch, reservations whose window has expired
    are removed; the request is dispatched only when the active-window sum plus
    the new reservation is within ``tokens_per_minute``. Otherwise the
    scheduler waits until enough reservations expire, then recalculates.
    Injectable ``clock`` / ``sleeper`` callables allow deterministic
    fake-clock tests.
    """

    WINDOW_SECONDS = 60.0

    def __init__(self, tokens_per_minute, clock=None, sleeper=None):
        if tokens_per_minute <= 0:
            raise ValueError("tokens_per_minute must be positive")
        self.capacity = float(tokens_per_minute)
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._reservations = []
        self.recorded_waits = []

    def active_tokens(self):
        """Prune expired windows and return the remaining active reservation sum."""
        now = self._clock()
        self._reservations = [(expiry, tokens)
                              for expiry, tokens in self._reservations if expiry > now]
        return sum(tokens for _, tokens in self._reservations)

    def reserve(self, tokens):
        if tokens > self.capacity:
            raise ValueError("Request exceeds the complete input+output token allowance")
        while True:
            active = self.active_tokens()
            if active + tokens <= self.capacity:
                now = self._clock()
                self._reservations.append((now + self.WINDOW_SECONDS, tokens))
                return
            now = self._clock()
            earliest_expiry = min(expiry for expiry, _ in self._reservations)
            wait = max(earliest_expiry - now, 0.0)
            self._sleep(wait)
            self.recorded_waits.append(wait)


def execute(client, plan, save, scheduler=None, stop_on_failure=False):
    provider_name = plan.get("provider", "openai")
    if provider_name not in {"openai", "groq"}:
        raise ValueError("Unsupported evaluation provider")
    if provider_name == "groq" and not plan.get("live_supported", False):
        raise ValueError(
            "Groq evaluation is dry-run only; prepare a separate live budget first")
    max_requests = plan.get("max_requests", MAX_REQUESTS)
    output_cap = plan.get("max_output_tokens_per_request", MAX_OUTPUT_TOKENS)
    meter = Meter(client, max_requests=max_requests)
    provider_class = GroqResponsesProvider if provider_name == "groq" else OpenAIResponsesProvider
    model = plan.get("model", GROQ_MODEL if provider_name == "groq" else MODEL)
    provider = provider_class(
        api_key="injected-client", model=model, timeout=TIMEOUT,
        max_output_tokens=output_cap, client=meter,
    )

    plan_case_ids = [r["case"] for r in plan["requests"]]
    unique_case_ids = list(dict.fromkeys(plan_case_ids))
    all_cases_by_id = {c["id"]: c for c in cases()}
    target_cases = [all_cases_by_id[cid]
                    for cid in unique_case_ids if cid in all_cases_by_id]

    rates = plan.get("rates_usd_per_million") or (
        {"input": GROQ_INPUT_USD_PER_MILLION, "output": GROQ_OUTPUT_USD_PER_MILLION}
        if provider_name == "groq"
        else {"input": INPUT_USD_PER_MILLION, "output": OUTPUT_USD_PER_MILLION}
    )
    max_cost = plan.get("max_estimated_cost_usd")
    per_request_usd = max_cost / max_requests if max_cost else 0.0

    complete_by_key = {(r["case"], r["task"]): r["complete_token_estimate"]
                       for r in plan["requests"]}

    report = {"mode": "live", "plan": plan, "cases": target_cases, "results": [],
              "semantic_quality": "pending_human_review"}
    save(report)  # Persist before the first request; checkpoint every result.

    for case in report["cases"]:
        case_tasks = [r["task"]
                      for r in plan["requests"] if r["case"] == case["id"]]
        for task in case_tasks:
            if scheduler is not None:
                required = complete_by_key.get((case["id"], task), 0)
                scheduler.reserve(required)
            started = time.perf_counter()
            row = {"case": case["id"], "task": task, "status": "provider_failure",
                   "output": None, "human_review": {"reviewer": None, "scores": None, "notes": None}}
            try:
                output = dispatch(provider, task, case["source"])
                row["output"] = output.model_dump(mode="json")
                row["status"] = "validation_failure"
                row["checks"] = check_output(task, output, case["source"])
                row["status"] = "contract_pass"
            except Exception as error:
                # Upstream exception strings may include credentials or payloads.
                # The phase + safe provider status identify the failure boundary;
                # record only exception class names, never messages. When the
                # adapter wrapped an underlying parse/transport error, its class
                # is the useful diagnostic (e.g. ValidationError for out-of-
                # contract structured content).
                cause = getattr(error, "__cause__", None)
                row["failure_type"] = (
                    type(cause).__name__ if cause is not None else type(error).__name__)
                row.update(validation_diagnostics(error))
            row.update(meter.last)
            row["latency_seconds"] = round(time.perf_counter() - started, 3)
            usage = row.get("usage")
            row["estimated_cost_usd"] = (
                (usage["input_tokens"] * rates["input"] +
                 usage["output_tokens"] * rates["output"]) / 1_000_000
                if usage else None)
            row["reserved_cost_usd"] = per_request_usd
            report["results"].append(row)
            report["attempted_requests"] = meter.calls
            report["known_usage_cost_usd"] = sum(
                r["estimated_cost_usd"] or 0 for r in report["results"])
            report["unknown_usage_requests"] = sum(
                r.get("usage") is None for r in report["results"])
            report["reserved_cost_usd"] = round(
                meter.calls * per_request_usd, 6)
            save(report)
            if stop_on_failure and row["status"] in {"provider_failure", "validation_failure"}:
                if row["status"] == "provider_failure":
                    report["stopped"] = "Provider failure; pilot stops without retry or fallback"
                else:
                    report["stopped"] = "Contract or evidence validation failure; pilot stops without retry or fallback"
                save(report)
                return report
            if usage and (usage["input_tokens"] > MAX_INPUT_TOKENS_ESTIMATE or usage["output_tokens"] > output_cap):
                report["stopped"] = "Provider usage exceeded planned allowance"
                save(report)
                return report
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="Explicitly authorize this synthetic API run")
    parser.add_argument("--pilot", action="store_true",
                        help="Run a 3-request pilot on the canonical case (profile, fit, pack)")
    parser.add_argument("--provider", choices=["openai", "groq"],
                        default="openai", help="Evaluation provider (default: openai)")
    parser.add_argument("--max-cost-usd", type=float,
                        help="Required live cost acknowledgement")
    parser.add_argument("--output", type=Path, required=True,
                        help="New report file; never overwrite evidence")
    args = parser.parse_args(argv)

    dotenv = _load_dotenv()

    try:
        plan = build_plan(args.provider, pilot=args.pilot, env=dotenv)
    except ValueError as error:
        parser.error(str(error))

    if args.live:
        if args.provider == "groq" and not args.pilot:
            parser.error(
                "Groq evaluation is pilot-only for live runs; use --pilot with --max-cost-usd")

        if args.provider == "groq":
            key_name = "JOBPILOT_GROQ_API_KEY"
        else:
            key_name = "JOBPILOT_OPENAI_API_KEY"

        expected_cost = plan.get("max_estimated_cost_usd")

        if os.environ.get("JOBPILOT_EVAL_ALLOW_LIVE") != "1" or args.max_cost_usd is None or round(args.max_cost_usd, 6) != round(expected_cost, 6):
            parser.error(
                f"Live requires JOBPILOT_EVAL_ALLOW_LIVE=1 and --max-cost-usd {expected_cost}")
        if not (os.environ.get(key_name) or dotenv.get(key_name)):
            parser.error(
                f"Live requires {key_name} in the process environment or .env")

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        plan_case_ids = [r["case"] for r in plan["requests"]]
        unique_case_ids = list(dict.fromkeys(plan_case_ids))
        all_cases_by_id = {c["id"]: c for c in cases()}
        target_cases = [all_cases_by_id[cid]
                        for cid in unique_case_ids if cid in all_cases_by_id]
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump({"mode": "planned", "plan": plan,
                       "cases": target_cases}, handle, indent=2)
    except OSError:
        parser.error(
            "Preflight failed or output exists/is unwritable; choose a new report path")

    if not args.live:
        mode_label = f"{args.provider} pilot" if args.pilot else args.provider
        print(
            f"Offline {mode_label} plan: {len(plan['requests'])} requests proposed; 0 sent.")
        return 0

    # Suppress SDK/HTTP debug logs even if enabled externally. Never log keys.
    logging.disable(logging.CRITICAL)
    from openai import OpenAI
    from app.services.ai_provider import GROQ_BASE_URL

    def save(report):
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(
            report, indent=2, ensure_ascii=True), encoding="utf-8")
        temporary.replace(args.output)

    try:
        groq_key = os.environ.get("JOBPILOT_GROQ_API_KEY") or dotenv.get("JOBPILOT_GROQ_API_KEY")
        openai_key = os.environ.get("JOBPILOT_OPENAI_API_KEY") or dotenv.get("JOBPILOT_OPENAI_API_KEY")
        if args.provider == "groq":
            client_kwargs = {
                "api_key": groq_key,
                "base_url": GROQ_BASE_URL,
                "timeout": TIMEOUT,
                "max_retries": 0,
            }
        else:
            client_kwargs = {
                "api_key": openai_key,
                "base_url": "https://api.openai.com/v1",
                "timeout": TIMEOUT,
                "max_retries": 0,
            }

        scheduler = None
        if plan.get("tokens_per_minute"):
            scheduler = TokenScheduler(plan["tokens_per_minute"])

        with OpenAI(**client_kwargs) as client:
            report = execute(client, plan, save,
                             scheduler=scheduler,
                             stop_on_failure=(plan.get("provider") == "groq"))
    except Exception:
        print(
            "Evaluation stopped; inspect the checkpoint report. Error details suppressed.")
        return 1

    print(
        f"Completed {report['attempted_requests']} requests; semantic quality requires human review.")
    return 0 if len(report["results"]) == plan["max_requests"] and all(r["status"] == "contract_pass" for r in report["results"]) and not report.get("stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
