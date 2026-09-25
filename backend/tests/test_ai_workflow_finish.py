"""Offline contract checks for the final AI profile, fit and pilot changes."""
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AIPilotDispatch, User
from app.schemas.job_fit import CandidateFact, JobFitResultResponse, ProviderJobFitOutput
from app.schemas.profile_suggestions import ALL_SUGGESTION_FIELDS, ProviderWireSuggestionOutput
from app.services import ai_usage, job_fit_service, interview_live_voice
from app.services.ai_provider import OpenAIResponsesProvider, ProviderFailure
from app.services.application_pack_service import PackError


def _wire_skills(value):
    return {"suggestions": [{"id": "skills-1", "field": "skills",
            "value": {"text": None, "experience": None, "education": None,
                      "language": None, "remote_preference": None,
                      "work_authorization": None, "salary": None, "skills": value},
            "evidence": [{"quote": "Skills: Python, PostgreSQL"}]}],
            "not_found": sorted(ALL_SUGGESTION_FIELDS - {"skills"}),
            "partial": False, "message": None}


def test_profile_skills_request_and_validation_use_the_same_strict_shape():
    calls = []
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: (
        calls.append(kw) or SimpleNamespace(status="completed",
                                            output_text=json.dumps(_wire_skills(["Python", "PostgreSQL"]))))))
    provider = OpenAIResponsesProvider(api_key="unused", model="synthetic", timeout=3,
                                       max_output_tokens=1000, client=client)
    result = provider.suggest("Skills: Python, PostgreSQL")
    assert result.suggestions[0].value == ["Python", "PostgreSQL"]
    schema = calls[0]["text"]["format"]["schema"]
    value = schema["$defs"]["ProviderWireValue"]
    assert set(value["required"]) == set(value["properties"])
    assert value["properties"]["skills"]["anyOf"][0]["type"] == "array"
    assert "every schema key" in calls[0]["instructions"]
    assert "unused key to null" in calls[0]["instructions"]
    assert calls[0]["store"] is False
    with pytest.raises(ProviderFailure, match="invalid_field_value"):
        provider.client.responses.create = lambda **kw: SimpleNamespace(
            status="completed", output_text=json.dumps(_wire_skills("Python, PostgreSQL")))
        provider.suggest("Skills: Python, PostgreSQL")


def test_job_fit_lists_only_quoted_unevidenced_required_or_preferred_skills():
    facts = [CandidateFact(id="fact-1", path="skills[0]", value="Python")]
    description = "Python required. Kubernetes required. Docker preferred. Leadership needed."
    items = [
        dict(id="req-1", text="Python", job_quote="Python required", importance="required",
             assessment="supported", explanation="Saved evidence", candidate_fact_ids=["fact-1"], skill_name="Python"),
        dict(id="req-2", text="Kubernetes", job_quote="Kubernetes required", importance="required",
             assessment="not_evidenced", explanation="No saved evidence", candidate_fact_ids=[], skill_name="Kubernetes"),
        dict(id="req-3", text="Docker", job_quote="Docker preferred", importance="preferred",
             assessment="not_evidenced", explanation="No saved evidence", candidate_fact_ids=[], skill_name="Docker"),
        dict(id="req-4", text="Leadership", job_quote="Leadership needed", importance="required",
             assessment="needs_clarification", explanation="Ambiguous", candidate_fact_ids=[], skill_name=None),
    ]
    output = ProviderJobFitOutput(requirements=items)
    assert job_fit_service.validate_output(output, description, facts)["requirements"][1]["assessment"] == "not_evidenced"
    assert [item["skill"] for item in output.missing_skills] == ["Kubernetes", "Docker"]
    assert "missing_skills" not in output.model_dump()
    assert [item["skill"] for item in JobFitResultResponse.model_validate(
        output.model_dump()).model_dump()["missing_skills"]] == ["Kubernetes", "Docker"]
    items[1]["skill_name"] = "AWS"
    partial = job_fit_service.validate_output(ProviderJobFitOutput(requirements=items), description, facts)
    assert "req-2" not in [item["id"] for item in partial["requirements"]]
    assert "Only requirements verified" in partial["summary"]


def test_production_pilot_claim_is_durable_and_single_use(db_session):
    owner = User(email=f"pilot-{uuid.uuid4()}@test.local", password_hash="synthetic")
    db_session.add(owner)
    db_session.commit()
    settings = get_settings().model_copy(update={"ENVIRONMENT": "production",
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_PILOT_ENABLED": True,
        "JOBPILOT_AI_PILOT_ACCOUNT_ID": str(owner.id)})
    ai_usage.claim_pilot_dispatch(db_session, owner.id, settings)
    claim = db_session.scalar(select(AIPilotDispatch).where(AIPilotDispatch.id == 1))
    assert claim.owner_id == owner.id and claim.feature == "profile" and claim.claimed_at
    with pytest.raises(ai_usage.AIUsageError, match="already been used"):
        ai_usage.claim_pilot_dispatch(db_session, owner.id, settings)
    with pytest.raises(ai_usage.AIUsageError, match="outside"):
        ai_usage.reserve(db_session, owner.id, settings, feature="fit")


def test_live_voice_flag_prevents_token_minting():
    settings = get_settings().model_copy(update={"JOBPILOT_LIVE_VOICE_ENABLED": False,
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_OPENAI_API_KEY": "synthetic"})
    assert interview_live_voice.available(settings) is False
    with pytest.raises(PackError, match="disabled"):
        interview_live_voice.token(None, uuid.uuid4(), uuid.uuid4(), settings)
