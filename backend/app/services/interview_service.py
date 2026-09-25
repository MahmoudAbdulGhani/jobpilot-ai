"""Immutable private snapshots, saved answers, bounded deduplicated AI operations."""
import copy
import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select

from app.models import (ApplicationPack, ApplicationPackVersion, CandidateProfile, InterviewSession,
    InterviewOperation, Resume, ResumeExtraction, User)
from app.schemas.interviews import InterviewOutput
from app.schemas.profile import CandidateProfileUpdate
from app.services import ai_usage
from app.services.application_pack_service import PackError, digest, owned_job
from app.services.profile_suggestion_service import provider_configuration, SuggestionError
from app.services.interview_provider import (PROMPT_VERSION, OpenAIInterviewProvider, TestInterviewProvider,
    InterviewProvider, request_bytes)

MAX_SOURCE_BYTES = 16000
DIMENSIONS = ("relevance", "clarity", "specificity", "technical_knowledge")
GUIDANCE = {
    "relevance": "Connect the answer directly to the question and the quoted job requirement; explain the connection.",
    "clarity": "Lead with the main point, then separate context, your reasoning or actions, and the outcome.",
    "specificity": "Describe your own contribution and a concrete example. Include outcomes only if true; say what is unknown.",
    "technical_knowledge": "Explain the mechanism, assumptions, alternatives and trade-offs. Distinguish experience from a hypothetical approach.",
}
FOCUSES = {
    "relevance": {"connect_to_question", "explain_relevance"},
    "clarity": {"lead_with_point", "separate_steps"},
    "specificity": {"own_contribution", "concrete_outcome"},
    "technical_knowledge": {"mechanism", "tradeoffs", "validation"},
}
ACTIONS = {
    "connect_to_question": "State which part of the question your example addresses, then return to that point at the end.",
    "explain_relevance": "Explain how your example relates to the quoted requirement; do not imply it proves experience you have not described.",
    "lead_with_point": "Open with a one-sentence answer before giving background. Remove context that does not help explain that answer.",
    "separate_steps": "Present context, actions or proposed steps, and outcome in a clear order. Distinguish your contribution from the team's.",
    "own_contribution": "Name one action you personally took and explain why. If you did not do it, explicitly frame the approach as hypothetical.",
    "concrete_outcome": "State what you actually observed and how you know. If no result was measured, say so; never invent a number.",
    "mechanism": "Explain how the proposed technique works and what assumptions it relies on; name what you would need to verify.",
    "tradeoffs": "Compare one alternative and explain the trade-off under the stated requirements. Separate opinion from tested results.",
    "validation": "Describe a test or observation that could check your explanation, including a failure case and what would change your approach.",
}
STRUCTURES = {
    "behavioral": "Example structure only — not candidate facts: Situation → your responsibility → actions → observed result → lesson. Use a real example or state that experience is missing.",
    "technical": "Example structure only — not candidate facts: Requirements → assumptions → approach → alternatives/trade-offs → validation. Label an untested proposal as hypothetical.",
}
QUESTION_TEXT = {
    "behavioral_example": "Describe a real situation relevant to this job excerpt. What was your responsibility, action and outcome? If you lack a real example, say so.",
    "technical_approach": "How would you approach this job requirement? Explain the mechanism, assumptions and how you would test your approach. Separate experience from a hypothetical proposal.",
    "clarify_action": "In this part of your answer, what did you personally do, and why? Describe only actions you actually took, or clarify that the proposal is hypothetical.",
    "explain_tradeoff": "Explain the assumptions and a trade-off behind this part of your answer. What alternative would you consider and how would you validate it?",
    "measure_result": "For this part of your answer, what outcome or observation can you support? If the result was not measured or is unknown, say so.",
}


def now():
    return datetime.now(timezone.utc)


def owner_lock(db, owner):
    if db.scalar(select(User.id).where(User.id == owner).with_for_update()) is None:
        raise PackError(404, "User not found")


def configuration(settings):
    try:
        name, model, key = provider_configuration(settings.model_copy(update={
            "JOBPILOT_AI_PROVIDER": settings.JOBPILOT_INTERVIEW_PROVIDER,
            "JOBPILOT_AI_MODEL": settings.JOBPILOT_INTERVIEW_MODEL}))
    except SuggestionError as error:
        raise PackError(error.status_code, error.message) from None
    return {"provider": name, "model": model, "reasoning": settings.JOBPILOT_INTERVIEW_REASONING_EFFORT,
        "max_output_tokens": settings.JOBPILOT_INTERVIEW_MAX_OUTPUT_TOKENS,
        "timeout": settings.JOBPILOT_INTERVIEW_TIMEOUT_SECONDS,
        "max_input_bytes": settings.JOBPILOT_INTERVIEW_MAX_INPUT_BYTES,
        "max_calls": settings.JOBPILOT_INTERVIEW_MAX_CALLS_PER_SESSION, "prompt_version": PROMPT_VERSION}, key


def provider_for(settings, config) -> InterviewProvider:
    current, key = configuration(settings)
    if any(current[k] != config[k] for k in ("provider", "model", "prompt_version")):
        raise PackError(409, "Interview provider configuration changed. Start a new session after reviewing it.")
    if config["provider"] == "deterministic-test":
        return TestInterviewProvider()
    return OpenAIInterviewProvider(key, config)


def capture(db, owner, job_id, selection):
    job = owned_job(db, owner, job_id)
    if not (job.description or "").strip():
        raise PackError(409, "Save a job description before practicing")
    source = {"job": {"id": str(job.id), "title": job.title, "company": job.company, "description": job.description}}
    if selection.resume_id:
        resume = db.scalar(select(Resume).where(Resume.id == selection.resume_id, Resume.owner_id == owner))
        if resume is None:
            raise PackError(404, "Reviewed CV not found")
        extraction = db.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume.id))
        if extraction is None or extraction.reviewed_at is None or extraction.status != "succeeded" or not (extraction.draft_text or "").strip():
            raise PackError(409, "Confirm nonempty extracted CV text before practicing")
        profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner))
        values = CandidateProfileUpdate.model_validate({name: getattr(profile, name)
            for name in CandidateProfileUpdate.model_fields}).model_dump(mode="json") if profile else {}
        source.update(source_kind="reviewed_cv", source_id=str(resume.id), source_name=resume.display_name,
            reviewed_at=extraction.reviewed_at.isoformat(), candidate_profile=values, cv_text=extraction.draft_text)
    else:
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == selection.pack_id,
            ApplicationPack.owner_id == owner, ApplicationPack.job_id == job_id))
        if pack is None:
            raise PackError(404, "Application pack not found for this job")
        version = db.scalar(select(ApplicationPackVersion).where(ApplicationPackVersion.pack_id == pack.id,
            ApplicationPackVersion.number == selection.pack_version))
        if version is None or version.approved_at is None or pack.status != "ready":
            raise PackError(409, "Choose an approved application-pack version")
        source.update(source_kind="approved_pack", source_id=str(pack.id), pack_version=version.number,
            approved_at=version.approved_at.isoformat(), candidate_profile=copy.deepcopy(pack.source_snapshot.get("profile", {})),
            cv_text="\n".join(b["text"] for b in version.cv["blocks"]),
            cover_letter_text="\n".join(b["text"] for b in version.cover_letter["blocks"]))
    if len(json.dumps(source, ensure_ascii=False).encode()) > MAX_SOURCE_BYTES:
        raise PackError(413, "Selected sources exceed the 16,000-byte interview limit. Review a shorter source; nothing was truncated.")
    return source


def preview(db, owner, job_id, selection, settings):
    source = capture(db, owner, job_id, selection)
    config, _ = configuration(settings)
    if selection.question_count + 1 > config["max_calls"]:
        raise PackError(422, "Question count exceeds the configured session request allowance")
    values = {"source_snapshot": source, "configuration": config, "mode": selection.mode, "question_count": selection.question_count}
    return {**values, "preview_hash": digest(values)}


def start(db, owner, job_id, body, settings):
    owner_lock(db, owner)
    hashed = digest({"job_id": str(job_id), **body.model_dump(mode="json")})
    existing = db.scalar(select(InterviewSession).where(InterviewSession.owner_id == owner, InterviewSession.request_key == body.request_key))
    if existing:
        if existing.request_hash != hashed:
            raise PackError(409, "This start key was already used with different choices")
        return existing
    if db.scalar(select(func.count()).select_from(InterviewSession).where(InterviewSession.owner_id == owner)) >= settings.JOBPILOT_INTERVIEW_MAX_SESSIONS_PER_USER:
        raise PackError(429, "Saved interview session limit reached. Delete an old session first.")
    prepared = preview(db, owner, job_id, body, settings)
    if prepared["preview_hash"] != body.preview_hash:
        raise PackError(409, "Sources or settings changed. Review a new preview before starting.")
    row = InterviewSession(owner_id=owner, job_id=job_id, request_key=body.request_key, request_hash=hashed,
        source_snapshot=prepared["source_snapshot"], configuration=prepared["configuration"],
        mode=body.mode, question_count=body.question_count, turns=[], status="ready", revision=0)
    db.add(row); db.commit()
    return row


def owned(db, owner, id, lock=False):
    q = select(InterviewSession).where(InterviewSession.id == id, InterviewSession.owner_id == owner).execution_options(populate_existing=True)
    row = db.scalar(q.with_for_update() if lock else q)
    if row is None:
        raise PackError(404, "Interview session not found")
    return row


def display_status(row, active):
    return "interrupted" if row.status == "generating" and (active is None or active.deadline < now()) else row.status


def public(db, row):
    operations = list(db.scalars(select(InterviewOperation).where(InterviewOperation.session_id == row.id)
        .order_by(InterviewOperation.created_at, InterviewOperation.id)))
    active = next((o for o in operations if o.id == row.active_operation), None)
    from app.models import InterviewLiveVoice
    live = db.get(InterviewLiveVoice, row.id)
    return {"id": row.id, "job_id": row.job_id, "status": display_status(row, active),
        "revision": row.revision, "mode": row.mode, "question_count": row.question_count,
        "configuration": row.configuration, "source_snapshot": row.source_snapshot, "turns": row.turns,
        "live_voice": None if live is None else {"status": live.status, "confirmed_turns": live.confirmed_turns},
        "created_at": row.created_at, "guidance": GUIDANCE, "actions": ACTIONS, "example_structures": STRUCTURES,
        "practice_actions": sorted({c["focus"] for t in row.turns if t.get("feedback")
            for c in t["feedback"].values() if c["assessment"] != "demonstrated"}),
        "practice_priorities": [name for name in DIMENSIONS if any(t.get("feedback") and
            t["feedback"][name]["assessment"] != "demonstrated" for t in row.turns)],
        "operations": [{"id": o.id, "step": o.step, "status": "interrupted" if o.status == "pending" and o.deadline < now() else o.status,
            "outcome": o.outcome, "usage": o.usage} for o in operations]}


def save_answer(db, owner, id, body):
    owner_lock(db, owner)
    row = owned(db, owner, id, True)
    if row.status == "generating":
        active = db.get(InterviewOperation, row.active_operation)
        if active.deadline < now():
            active.status, active.outcome = "failed", "interrupted"
            row.status = "interrupted"
    if row.status not in {"ready", "interrupted"} or not row.turns or row.turns[-1].get("feedback"):
        raise PackError(409, "This question is not editable. Refresh the session.")
    if body.revision != row.revision or body.question_number != len(row.turns):
        raise PackError(409, "Session changed; reload before saving")
    row.turns = copy.deepcopy(row.turns)
    row.turns[-1]["answer"] = body.answer
    row.revision += 1
    db.commit()
    return row


def request_payload(row):
    index = len(row.turns)
    category = ("behavioral" if index % 2 == 0 else "technical") if row.mode == "mixed" else row.mode
    allowed = ["technical_approach", "explain_tradeoff"] if category == "technical" else ["behavioral_example", "clarify_action", "measure_result"]
    return {"source": row.source_snapshot, "next_category": category, "allowed_strategies": allowed,
        "final": index == row.question_count,
        "prior_questions": [t["question"] for t in row.turns],
        "latest_answer": row.turns[-1]["answer"] if row.turns else None}


def validate_output(raw, payload):
    output = InterviewOutput.model_validate(raw)
    answer = payload["latest_answer"]
    if (output.feedback is None) != (answer is None) or (output.question is None) != payload["final"]:
        raise ValueError("Missing question or feedback")
    if output.feedback:
        for dimension in DIMENSIONS:
            criterion = getattr(output.feedback, dimension)
            if criterion.focus not in FOCUSES[dimension]:
                raise ValueError("Feedback focus does not match its dimension")
            if criterion.assessment == "insufficient_evidence":
                if criterion.answer_quotes:
                    raise ValueError("Insufficient-evidence assessment cannot assert supporting quotes")
            elif not criterion.answer_quotes:
                raise ValueError("Assessment lacks answer evidence")
            if any(not q.strip() or q not in answer for q in criterion.answer_quotes):
                raise ValueError("Feedback quote is not an exact answer passage")
    if output.question:
        q = output.question
        source = payload["source"]["job"]["description"] if q.source == "job" else answer
        if q.strategy not in payload["allowed_strategies"] or not source or not q.quote.strip() or q.quote not in source:
            raise ValueError("Question is not grounded in its permitted source")
        if (q.strategy in {"clarify_action", "measure_result", "explain_tradeoff"}) != (q.source == "answer"):
            raise ValueError("Follow-up must refer to the latest answer")
        if any(previous["strategy"] == q.strategy and previous["quote"] == q.quote for previous in payload["prior_questions"]):
            raise ValueError("Repeated question")
    return output


def advance(db, owner, id, body, settings):
    from app.services.privacy_service import require_consent
    require_consent(db, owner, "ai_interview")
    owner_lock(db, owner)
    row = owned(db, owner, id, True)
    hashed = digest(body.model_dump(mode="json"))
    existing = db.scalar(select(InterviewOperation).where(InterviewOperation.session_id == id, InterviewOperation.request_key == body.request_key))
    if existing:
        if existing.request_hash != hashed:
            raise PackError(409, "This request key was used with different content")
        return row
    if row.revision != body.revision or row.status == "completed":
        raise PackError(409, "Session changed or finished; reload before continuing")
    if row.status == "generating":
        active = db.get(InterviewOperation, row.active_operation)
        if active.deadline >= now():
            raise PackError(409, "A model request is already pending. Refresh; do not resubmit.")
        active.status, active.outcome = "failed", "interrupted"
        row.status = "interrupted"
    if row.turns and not row.turns[-1]["answer"].strip():
        raise PackError(422, "Save an answer first; you may explicitly say you do not know")
    ops = list(db.scalars(select(InterviewOperation).where(InterviewOperation.session_id == id)))
    if len(ops) >= min(row.configuration["max_calls"], settings.JOBPILOT_INTERVIEW_MAX_CALLS_PER_SESSION) or sum(o.step == len(row.turns) for o in ops) >= 2:
        raise PackError(429, "Interview request allowance exhausted; saved answers remain available")
    payload = request_payload(row)
    if request_bytes(payload, row.configuration) > min(row.configuration["max_input_bytes"], settings.JOBPILOT_INTERVIEW_MAX_INPUT_BYTES):
        raise PackError(413, "Interview request exceeds the input limit. Your saved answer is retained.")
    provider = provider_for(settings, row.configuration)
    try:
        token = ai_usage.reserve(db, owner, settings.model_copy(update={"JOBPILOT_AI_TIMEOUT_SECONDS": row.configuration["timeout"]}), feature="interview")
    except ai_usage.AIUsageError as error:
        raise PackError(error.status_code, error.message) from None
    operation = InterviewOperation(id=uuid.uuid4(), session_id=id, request_key=body.request_key, request_hash=hashed,
        step=len(row.turns), status="pending", deadline=now()+timedelta(seconds=row.configuration["timeout"]+10))
    db.add(operation)
    row.status, row.active_operation = "generating", operation.id
    row.revision += 1
    op_id, timeout = operation.id, row.configuration["timeout"]
    db.commit()  # Saved answers and dispatch claim precede network I/O.
    try:
        ai_usage.dispatch_guard(db, owner)
        require_consent(db, owner, "ai_interview")
    except Exception:
        row.status, row.active_operation = "interrupted", None
        operation.status, operation.outcome = "failed", "consent_or_account_denied"
        ai_usage.release(db, owner, token)
        db.commit()
        raise
    result, output, failure = None, None, None
    try:
        result = ai_usage.bounded_call(lambda: provider.practice(payload), timeout)
        output = validate_output(result.output, payload)
    except Exception as error:
        from app.services.ai_provider import ProviderFailure
        failure = (str(error) if isinstance(error, ProviderFailure) and str(error) in
            {"incomplete_or_refused", "provider_or_validation_failure"} else "invalid_output" if result else "provider_unavailable")
    owner_lock(db, owner)
    try:
        row = owned(db, owner, id, True)
    except PackError:
        ai_usage.release(db, owner, token); db.commit()
        raise
    operation = db.get(InterviewOperation, op_id, populate_existing=True)
    ai_usage.release(db, owner, token)
    if row.active_operation != op_id or operation.status != "pending":
        db.commit()
        return row  # A late result cannot overwrite a newer operation.
    operation.usage = result.usage if result else None
    if failure or operation.deadline < now():
        row.status, operation.status, operation.outcome = "interrupted", "failed", failure or "interrupted"
    else:
        turns = copy.deepcopy(row.turns)
        if output.feedback:
            turns[-1]["feedback"] = output.feedback.model_dump(mode="json")
        if output.question:
            q = output.question.model_dump(mode="json")
            turns.append({"number": len(turns)+1, "category": payload["next_category"],
                "question": q, "text": QUESTION_TEXT[q["strategy"]], "answer": "", "feedback": None})
        row.turns = turns
        row.status = "completed" if payload["final"] else "ready"
        operation.status, operation.outcome = "succeeded", "validated"
    row.revision += 1
    db.commit()
    return row


def delete(db, owner, id):
    owner_lock(db, owner)
    row = owned(db, owner, id, True)
    db.delete(row); db.commit()
