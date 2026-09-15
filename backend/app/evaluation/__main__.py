"""Run with --help. Default is an offline request plan, even with credentials set."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from types import SimpleNamespace

from app.evaluation.fixtures import cases
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
MAX_INPUT_TOKENS_ESTIMATE = 32_000
MAX_OUTPUT_TOKENS = 4_000
TIMEOUT = 60
INPUT_USD_PER_MILLION = 0.25
OUTPUT_USD_PER_MILLION = 2.0
PER_REQUEST_USD = 0.016
MAX_COST_USD = 0.24
TASKS = {"profile": PROMPT_VERSION, "fit": JOB_FIT_PROMPT_VERSION, "pack": PACK_PROMPT_VERSION}


def dispatch(provider, task, source):
    if task == "profile":
        return provider.suggest(source["cv_text"])
    if task == "fit":
        return provider.analyze(source["job"]["description"],
                                [CandidateFact.model_validate(f) for f in source["profile_facts"]])
    return provider.create_pack(source)


class Planned(ProviderFailure):
    pass


def request_plan(task, source, provider_name="openai"):
    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        raise Planned()

    provider_class = GroqResponsesProvider if provider_name == "groq" else OpenAIResponsesProvider
    provider = provider_class(
        api_key="offline-placeholder", model=GROQ_MODEL if provider_name == "groq" else MODEL, timeout=TIMEOUT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        client=SimpleNamespace(responses=SimpleNamespace(parse=capture)),
    )
    try:
        dispatch(provider, task, source)
    except Planned:
        pass
    # Include schema/instructions, not just source text. UTF-8 byte count is a
    # deliberately conservative token estimate, plus protocol/schema allowance.
    serializable = {**captured, "text_format": captured["text_format"].model_json_schema()}
    encoded = json.dumps(serializable, ensure_ascii=True, sort_keys=True).encode()
    estimate = len(encoded) + 2048
    if estimate > MAX_INPUT_TOKENS_ESTIMATE:
        raise ValueError("Request exceeds the evaluation input allowance")
    if captured.get("store") is not False or "tools" in captured:
        raise ValueError("Evaluation requires tool-free, nonstored requests")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "input_token_estimate": estimate}


def build_plan(provider_name="openai"):
    if provider_name not in {"openai", "groq"}:
        raise ValueError("Unsupported evaluation provider")
    entries = []
    for case in cases():
        for task, version in TASKS.items():
            entries.append({"case": case["id"], "task": task, "prompt_version": version,
                            **request_plan(task, case["source"], provider_name)})
    if len(entries) != MAX_REQUESTS:
        raise ValueError("Fixture count changed; review the request and cost budget")
    return {"provider": provider_name, "model": GROQ_MODEL if provider_name == "groq" else MODEL, "max_requests": MAX_REQUESTS,
            "max_input_tokens_estimate_per_request": MAX_INPUT_TOKENS_ESTIMATE,
            "max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
            "timeout_seconds": TIMEOUT, "retries": 0,
            "live_supported": provider_name == "openai",
            "max_estimated_cost_usd": MAX_COST_USD if provider_name == "openai" else None,
            "rates_usd_per_million": {"input": INPUT_USD_PER_MILLION, "output": OUTPUT_USD_PER_MILLION} if provider_name == "openai" else None,
            "requests": entries}


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


class Meter:
    """Observe usage without changing the production adapter or printing errors."""
    def __init__(self, client):
        self.client = client
        self.responses = self
        self.calls = 0
        self.last = {}

    def parse(self, **kwargs):
        if self.calls >= MAX_REQUESTS:
            raise ProviderFailure("Evaluation request budget exhausted")
        self.calls += 1  # Failures consume the allowance too; never retry.
        self.last = {"provider_status": "transport_or_parse_failure", "usage": None}
        response = self.client.responses.parse(**kwargs, service_tier="default")
        usage = getattr(response, "usage", None)
        self.last = {"provider_status": getattr(response, "status", "unknown"),
                     "returned_model": getattr(response, "model", None), "usage": None}
        if usage is not None:
            self.last["usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                "reasoning_tokens": getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", None)}
        return response


def execute(client, plan, save):
    if plan.get("provider", "openai") != "openai":
        raise ValueError("Groq evaluation is dry-run only; prepare a separate live budget first")
    meter = Meter(client)
    provider = OpenAIResponsesProvider(api_key="injected-client", model=MODEL,
        timeout=TIMEOUT, max_output_tokens=MAX_OUTPUT_TOKENS, client=meter)
    report = {"mode": "live", "plan": plan, "cases": cases(), "results": [],
              "semantic_quality": "pending_human_review"}
    save(report)  # Persist before the first request; checkpoint every result.
    for case in report["cases"]:
        for task in TASKS:
            started = time.perf_counter()
            row = {"case": case["id"], "task": task, "status": "provider_failure",
                   "output": None, "human_review": {"reviewer": None, "scores": None, "notes": None}}
            try:
                output = dispatch(provider, task, case["source"])
                row["output"] = output.model_dump(mode="json")
                row["status"] = "validation_failure"
                row["checks"] = check_output(task, output, case["source"])
                row["status"] = "contract_pass"
            except Exception:
                # Upstream exception strings may include credentials or payloads.
                # The phase + safe provider status identify the failure boundary.
                pass
            row.update(meter.last)
            row["latency_seconds"] = round(time.perf_counter() - started, 3)
            usage = row.get("usage")
            row["estimated_cost_usd"] = (
                (usage["input_tokens"] * INPUT_USD_PER_MILLION + usage["output_tokens"] * OUTPUT_USD_PER_MILLION) / 1_000_000
                if usage else None)
            row["reserved_cost_usd"] = PER_REQUEST_USD
            report["results"].append(row)
            report["attempted_requests"] = meter.calls
            report["known_usage_cost_usd"] = sum(r["estimated_cost_usd"] or 0 for r in report["results"])
            report["unknown_usage_requests"] = sum(r.get("usage") is None for r in report["results"])
            report["reserved_cost_usd"] = round(meter.calls * PER_REQUEST_USD, 6)
            save(report)
            if usage and (usage["input_tokens"] > MAX_INPUT_TOKENS_ESTIMATE or usage["output_tokens"] > MAX_OUTPUT_TOKENS):
                report["stopped"] = "Provider usage exceeded planned allowance"
                save(report)
                return report
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly authorize this synthetic API run")
    parser.add_argument("--provider", choices=["openai", "groq"], default="openai", help="Groq currently supports offline planning only")
    parser.add_argument("--max-cost-usd", type=float, help="Required live cost acknowledgement: 0.24")
    parser.add_argument("--output", type=Path, required=True, help="New report file; never overwrite evidence")
    args = parser.parse_args(argv)
    if args.live and args.provider == "groq":
        parser.error("Groq evaluation is dry-run only; prepare a separate live budget first")
    if args.live and (os.environ.get("JOBPILOT_EVAL_ALLOW_LIVE") != "1" or args.max_cost_usd != MAX_COST_USD):
        parser.error("Live requires JOBPILOT_EVAL_ALLOW_LIVE=1 and --max-cost-usd 0.24")
    if args.live and not os.environ.get("JOBPILOT_OPENAI_API_KEY"):
        parser.error("Live requires JOBPILOT_OPENAI_API_KEY in the process environment")
    # No .env loading, Settings construction, database access, or provider factory.
    # Application AI flags and test-provider guards are entirely unchanged.
    try:
        plan = build_plan(args.provider)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump({"mode": "planned", "plan": plan, "cases": cases()}, handle, indent=2)
    except (ValueError, OSError):
        parser.error("Preflight failed or output exists/is unwritable; choose a new report path")
    if not args.live:
        print(f"Offline {args.provider} plan: 15 requests proposed; 0 sent.")
        return 0
    # Suppress SDK/HTTP debug logs even if enabled externally. Never log keys.
    logging.disable(logging.CRITICAL)
    from openai import OpenAI

    def save(report):
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        temporary.replace(args.output)

    try:
        with OpenAI(api_key=os.environ["JOBPILOT_OPENAI_API_KEY"],
                    base_url="https://api.openai.com/v1", timeout=TIMEOUT, max_retries=0) as client:
            report = execute(client, plan, save)
    except Exception:
        print("Evaluation stopped; inspect the checkpoint report. Error details suppressed.")
        return 1
    print(f"Completed {report['attempted_requests']} requests; semantic quality requires human review.")
    return 0 if len(report["results"]) == MAX_REQUESTS and all(r["status"] == "contract_pass" for r in report["results"]) and not report.get("stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
