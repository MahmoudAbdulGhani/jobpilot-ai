"""One canonical synthetic profile or pack request through the production adapter; dry by default."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import re

import httpx
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from app.schemas.application_packs import PackProviderOutput

from app.evaluation import __main__ as evaluation
from app.evaluation.fixtures import cases
from app.evaluation.validation_diagnostics import validation_diagnostics
from app.schemas.profile_suggestions import GroqProfileOutput
from app.services.ai_provider import GROQ_BASE_URL, GroqResponsesProvider, OpenAIResponsesProvider, ProviderFailure

# Only this diagnostic retains selected body fields. It cannot take arbitrary input.
# Unknown words, names, addresses, numbers and supplied credentials are redacted.
_WORDS = frozenset("""a an the this that is are was were be been to of for from with without
and or not no in on at by as it its please your request response error invalid valid failed
failure generate generated generation validate validation json schema expected actual match
matches does do output input text format type code message failed_generation details more see
adjust prompt strict true false null object array string number integer boolean properties
required additionalProperties headline evidence quote backend engineer max_output_tokens tokens
token maximum max minimum min limit length completion reached before after document unexpected
missing extra property field value supported unsupported model parameter schema_validation_failed
json_validate_failed invalid_request_error invalid_json_schema syntax parse parsing end empty
truncated incomplete completed refusal refused schema_name anyOf const enum items minLength
maxLength minItems maxItems defs ref cannot could unable exceeded exhausted reasoning budget
constrained decoding must should contain contains include includes only provided given found got
check malformed allowed at path root character characters suggestions partial id value message
location skills experience education languages job_title organization period notes school degree
proficiency name providerwiresuggestionoutput providerexperienceentry headlinesuggestion
locationsuggestion skillssuggestion providerexperiencesuggestion educationsuggestion
languagesuggestion experienceentry educationentry languageentry python postgresql beirut cedar
demo bsc computer science university built booking api project profile strong schema error
pattern too short long additional property unexpected invalid request required
cv cover_letter review_notes blocks kind paragraph bullet heading fact_id cv_quote pack
packprovideroutput providerdocument providerblock claimevidence
""".casefold().split())


def redacted(value, limit=2048, secrets=()):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=True)
    if not isinstance(value, str):
        return {"supplied": value is not None, "text": None, "truncated": False}
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[redacted]")
    truncated = len(value) > limit
    value = value[:limit]
    value = re.sub(r"[A-Za-z0-9_@/+=-]+",
                   lambda m: m.group() if m.group().casefold() in _WORDS else "[redacted]", value)
    return {"supplied": True, "text": value[:limit], "truncated": truncated or len(value) > limit}


def usage_from(body):
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    result = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")
              if type(usage.get(key)) is int and 0 <= usage[key] <= 10**12}
    details = usage.get("output_tokens_details")
    if isinstance(details, dict) and type(details.get("reasoning_tokens")) is int and 0 <= details["reasoning_tokens"] <= 10**12:
        result["reasoning_tokens"] = details["reasoning_tokens"]
    return result or None


class SyntheticTransport(httpx.BaseTransport):
    """Guard one serialized request and capture before the SDK can lose a response."""
    def __init__(self, inner, request_hash, secrets=(), task="profile", base_url=GROQ_BASE_URL):
        if base_url not in (GROQ_BASE_URL, "https://api.openai.com/v1"):
            raise ValueError("Unsupported diagnostic endpoint")
        self.base_url = base_url
        self.task = task
        self.inner, self.request_hash, self.secrets = inner, request_hash, secrets
        self.count = 0
        self.details = {}

    def handle_request(self, request):
        if self.count or str(request.url) != self.base_url + "/responses" or request.method != "POST":
            raise RuntimeError("Diagnostic permits exactly one canonical request")
        if hashlib.sha256(request.content).hexdigest() != self.request_hash:
            raise RuntimeError("Diagnostic serialization changed")
        self.count += 1
        response = self.inner.handle_request(request)
        self.details["http_status"] = response.status_code
        response.read()
        if len(response.content) > 131072:
            self.details["capture_skipped"] = "response_over_128_KiB"
            return response
        try:
            body = response.json()
        except ValueError:
            self.details["capture_skipped"] = "non_json_response"
            return response
        if not isinstance(body, dict):
            return response
        self.details["usage"] = usage_from(body)
        status = body.get("status")
        self.details["provider_status"] = status if status in ("completed", "failed", "incomplete", "in_progress") else None
        error = body.get("error")
        if not isinstance(error, dict):
            error = body if response.status_code >= 400 else {}
        self.details["provider_explanation"] = redacted(error.get("message"), 2048, self.secrets)
        self.details["failed_generation"] = redacted(error.get("failed_generation"), 4096, self.secrets)
        failed = error.get("failed_generation")
        if isinstance(failed, str) and len(failed) <= 32768:
            self.check_generation(failed, "failed_generation")
        # Retain bounded returned output text for SDK parsing failures; never reasoning.
        text = []
        complete_text = []
        for item in body.get("output", []) if isinstance(body.get("output"), list) else []:
            if isinstance(item, dict) and item.get("type") == "message":
                for part in item.get("content", []) if isinstance(item.get("content"), list) else []:
                    if isinstance(part, dict) and part.get("type") in ("output_text", "refusal"):
                        value = part.get("text", part.get("refusal"))
                        if isinstance(value, str):
                            text.append(value[:4096])
                            complete_text.append(value)
                        if len(text) >= 4:
                            break
            if len(text) >= 4:
                break
        if self.task == "pack" and complete_text:
            joined = "\n".join(complete_text)
            if len(joined) <= 32768:
                self.check_generation(joined, "returned_generation")
        if text:
            self.details["returned_text"] = redacted("\n".join(text), 4096, self.secrets)
        reason = body.get("incomplete_details")
        if isinstance(reason, dict):
            self.details["incomplete_reason"] = redacted(reason.get("reason"), 256, self.secrets)
        return response

    def check_generation(self, raw, prefix):
        try:
            if self.task == "profile":
                parsed = GroqProfileOutput.model_validate_json(raw).to_domain()
            else:
                parsed = PackProviderOutput.model_validate_json(raw)
                # The SDK makes every wire property required. Check fields_set
                # before defaults can conceal missing nullable fields or notes.
                errors = []
                def visit(value, path=()):
                    if isinstance(value, BaseModel):
                        for name in type(value).model_fields:
                            if name not in value.model_fields_set:
                                errors.append({"type": "missing", "loc": path + (name,), "input": None})
                            else:
                                visit(getattr(value, name), path + (name,))
                    elif isinstance(value, list):
                        for index, item in enumerate(value):
                            visit(item, path + (index,))
                visit(parsed)
                if errors:
                    raise ValidationError.from_exception_data("PackProviderOutput", errors)
            self.details[prefix + "_local_parse"] = "passed"
            try:
                self.details[prefix + "_checks"] = evaluation.check_output(self.task, parsed, cases()[0]["source"])
            except Exception:
                self.details[prefix + "_checks"] = "evidence_rejected"
        except ValidationError as failure:
            self.details[prefix + "_local_parse"] = "failed"
            self.details[prefix + "_validation"] = validation_diagnostics(failure)

    def close(self):
        self.inner.close()


def prepared_request(task="profile", provider_name="groq"):
    if provider_name not in ("groq", "openai") or (provider_name == "openai" and task != "pack"):
        raise ValueError("OpenAI comparison is pack-only")
    base_url = GROQ_BASE_URL if provider_name == "groq" else "https://api.openai.com/v1"
    provider_class = evaluation.evaluation_provider(provider_name, "minimal" if provider_name == "openai" else None)
    model = evaluation.GROQ_MODEL if provider_name == "groq" else evaluation.MODEL
    cap = (evaluation.MAX_OUTPUT_TOKENS if provider_name == "openai" else
           evaluation.GROQ_PROFILE_MAX_OUTPUT_TOKENS if task == "profile" else evaluation.GROQ_PACK_MAX_OUTPUT_TOKENS)
    if task not in ("profile", "pack"):
        raise ValueError("Unsupported synthetic task")
    captured = []
    def capture(request):
        captured.append(request.content)
        return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
    with OpenAI(api_key="synthetic", base_url=base_url, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(capture))) as client:
        try:
            provider = provider_class(api_key="unused", model=model, timeout=60,
                max_output_tokens=cap, client=evaluation.Meter(client))
            evaluation.dispatch(provider, task, cases()[0]["source"])
        except ProviderFailure:
            pass
    assert len(captured) == 1
    return captured[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("groq", "openai"), default="groq")
    parser.add_argument("--task", choices=("profile", "pack"), default="profile")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-cost-usd", type=Decimal)
    parser.add_argument("--dry-report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.provider == "openai" and args.task != "pack":
        parser.error("OpenAI comparison is pack-only")
    base_url = GROQ_BASE_URL if args.provider == "groq" else "https://api.openai.com/v1"
    plan = evaluation.build_plan(args.provider, pilot=True, task=args.task, env={},
                                 pack_reasoning="minimal" if args.provider == "openai" else None)
    if args.provider == "groq" and plan["tokens_per_minute"] != 8000:
        parser.error("This diagnostic requires the existing 8,000 TPM limit")
    request = prepared_request(args.task, args.provider)
    if hashlib.sha256(request).hexdigest() != plan["requests"][0]["sha256"]:
        parser.error("Prepared request differs from the plan")
    if args.live:
        if os.environ.get("JOBPILOT_EVAL_ALLOW_LIVE") != "1" or args.max_cost_usd != Decimal(str(plan["max_estimated_cost_usd"])):
            parser.error("Explicit live gate and exact planner budget are required")
        if not args.dry_report or json.loads(args.dry_report.read_text())["plan"] != plan:
            parser.error("A matching dry report is required")
    initial = {"mode": "planned", "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "actual_request_count": 0, "plan": plan, "request": json.loads(request)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(initial, handle, indent=2)
    if not args.live:
        print(json.dumps(initial, indent=2))
        return 0
    logging.disable(logging.CRITICAL)
    config = evaluation._load_dotenv()
    key_name = "JOBPILOT_GROQ_API_KEY" if args.provider == "groq" else "JOBPILOT_OPENAI_API_KEY"
    key = os.environ.get(key_name) or config.get(key_name)
    if not key:
        parser.error("Selected provider credential unavailable")
    secrets = [key] + [v for k, v in {**config, **os.environ}.items() if isinstance(v, str) and v and
                      any(word in k.upper() for word in ("SECRET", "PASSWORD", "TOKEN", "API_KEY"))]
    transport = SyntheticTransport(httpx.HTTPTransport(retries=0), plan["requests"][0]["sha256"], secrets, task=args.task, base_url=base_url)
    def save(report):
        if args.task == "pack":
            for row in report.get("results", []):
                if row.get("status") == "contract_pass" and (
                    transport.details.get("returned_generation_local_parse") != "passed"
                    or transport.details.get("returned_generation_checks") != {}
                ):
                    row["status"] = "validation_failure"
                    row["diagnostic_rejection"] = "Required wire fields or evidence not verified"
        safe = deepcopy(report)
        safe["created_at_utc"] = initial["created_at_utc"]
        safe["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        safe["actual_request_count"] = transport.count
        safe["synthetic_diagnostic"] = transport.details
        for row in safe.get("results", []):
            if row.get("output") is not None:
                row["output_redacted"] = redacted(row.pop("output"), 8192, secrets)
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(safe, indent=2), encoding="utf-8")
        temporary.replace(args.output)
    with OpenAI(api_key=key, base_url=base_url, max_retries=0, timeout=60,
                http_client=httpx.Client(transport=transport, timeout=60, follow_redirects=False)) as client:
        report = evaluation.execute(client, plan, save, scheduler=evaluation.TokenScheduler(8000) if args.provider == "groq" else None, stop_on_failure=True)
    print(f"Stopped after {transport.count} HTTP attempt; see {args.output}")
    return 0 if report["results"][0]["status"] == "contract_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
