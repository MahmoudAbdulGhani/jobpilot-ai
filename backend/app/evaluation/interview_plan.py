"""Offline only: capture one synthetic production-adapter request. No live switch."""
import hashlib
import json
from decimal import Decimal, ROUND_CEILING
from types import SimpleNamespace
import httpx
from openai import OpenAI
from app.core.config import get_settings
from app.evaluation.fixtures import cases
from app.services.ai_provider import ProviderFailure
from app.services.interview_provider import OpenAIInterviewProvider, request_bytes, PROMPT_VERSION
from app.services.interview_service import request_payload
from app.schemas.profile import CandidateProfileUpdate


def synthetic_payload():
    source = next(c['source'] for c in cases() if c['id']=='strong')
    snapshot = {"job": {"id":"00000000-0000-0000-0000-000000000001", **{k:source['job'][k] for k in ('title','company','description')}},
        "source_kind":"reviewed_cv", "source_id":"00000000-0000-0000-0000-000000000002",
        "source_name":"strong synthetic CV", "reviewed_at":source['reviewed_at'], "cv_text":source['cv_text'],
        "candidate_profile":CandidateProfileUpdate.model_validate({"headline":"Backend engineer", "skills":["Python","PostgreSQL"],
            "experience":[{"title":"Engineer","organization":"Cedar Demo","period":"2021-2024","notes":"Built a booking API"}],
            "education":[{"school":"Example University","degree":"BSc","field":"Computer Science","period":"2020"}]}).model_dump(mode='json')}
    row = SimpleNamespace(mode='mixed', question_count=2, source_snapshot=snapshot, turns=[{
        "question":{"strategy":"behavioral_example","source":"job","quote":"Build booking APIs."},
        "answer":"I built a booking API at Cedar Demo. My saved skills include Python and PostgreSQL, but I have not established which technologies the project used."}])
    return request_payload(row)


def build_plan():
    settings = get_settings()
    config = {"provider": settings.JOBPILOT_INTERVIEW_PROVIDER, "model": settings.JOBPILOT_INTERVIEW_MODEL,
        "reasoning": settings.JOBPILOT_INTERVIEW_REASONING_EFFORT,
        "max_output_tokens": settings.JOBPILOT_INTERVIEW_MAX_OUTPUT_TOKENS,
        "timeout": settings.JOBPILOT_INTERVIEW_TIMEOUT_SECONDS, "prompt_version": PROMPT_VERSION}
    payload = synthetic_payload()
    if request_bytes(payload, config) > settings.JOBPILOT_INTERVIEW_MAX_INPUT_BYTES:
        raise ValueError("Prepared request exceeds the configured interview input bound")
    captures = []
    def capture(request):
        captures.append(request.content)
        return httpx.Response(200,json={"id":"offline-plan","object":"response","created_at":0,
            "model":config["model"],"status":"incomplete","incomplete_details":{"reason":"max_output_tokens"},"output":[]})
    with OpenAI(api_key="offline-placeholder",max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(capture))) as client:
        try:
            OpenAIInterviewProvider("offline-placeholder",config,client).practice(payload)
        except ProviderFailure:
            pass
    assert len(captures)==1
    raw=captures[0];wire=json.loads(raw)
    assert wire['store'] is False and 'tools' not in wire and wire['text']['format']['strict'] is True
    reservation=len(raw)+2048  # UTF-8 bytes plus protocol allowance; not measured tokenizer usage.
    cost=(Decimal(reservation)*Decimal('0.25')+Decimal(config['max_output_tokens'])*Decimal('2'))/Decimal(1000000)
    return {"mode":"offline_only", "live_requests_sent":0, "planned_live_requests":1,
        "case":"strong synthetic answer assessment and one technical follow-up", "configuration":config,
        "serialized_request_bytes":len(raw), "request_sha256":hashlib.sha256(raw).hexdigest(),
        "input_token_reservation":reservation,"output_token_cap":config['max_output_tokens'],
        "total_token_reservation":reservation+config['max_output_tokens'],
        "calculated_estimate_usd":str(cost),"estimated_budget_ceiling_usd":str(cost.quantize(Decimal('0.000001'),rounding=ROUND_CEILING)),
        "pricing_source":"https://developers.openai.com/api/docs/models/gpt-5-mini",
        "pricing_assumption":"Standard uncached input USD 0.25/M, output USD 2/M; account billing unverified",
        "acceptance":["completed required-field-valid output", "all non-insufficient assessments cite exact answer passages",
            "permitted technical question grounded in job or latest answer", "no invented project/technology relationship",
            "separate human review of rubric quality and relevance; no hiring prediction"],
        "execution":"No live runner is exposed by this module. A separately authorized one-call runner must refresh this plan and enforce its budget before dispatch."}


if __name__ == '__main__':
    print(json.dumps(build_plan(),indent=2))
