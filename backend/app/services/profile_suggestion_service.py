import hashlib
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import CandidateProfile, ProfileSuggestionSet, Resume, ResumeExtraction
from app.schemas.profile import CandidateProfileUpdate
from app.schemas.profile_suggestions import ProfileSuggestion, ProviderSuggestionOutput
from app.services.ai_provider import (
    DeterministicTestProvider,
    OpenAIResponsesProvider,
    GroqResponsesProvider,
    PROMPT_VERSION,
    ProviderFailure,
)
from app.core.db import SessionLocal


_PROFILE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="profile-suggestions")


_CONTACT_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE)
_CONTACT_PHONE = re.compile(
    r"(?:\+\d[\d\s().-]{5,})"
    r"|(?:\b\d{2,4}[\s.-]\d{2,4}[\s.-]\d{3,4}\b)"
    r"|(?:\b\d{9,10}\b)"
)


def _is_contact_details(value: str) -> bool:
    """A location or skills suggestion may never contain contact details."""
    return bool(_CONTACT_EMAIL.search(value) or _CONTACT_PHONE.search(value))


class SuggestionError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def profile_revision(profile: CandidateProfile | None) -> str:
    return "none" if profile is None else profile.updated_at.isoformat()


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def provider_configuration(settings: Settings):
    """Resolve metadata without constructing a client; enforce the same gates for UI and generation."""
    if not settings.JOBPILOT_AI_ENABLED:
        raise SuggestionError(503, "AI features are disabled.")
    if settings.JOBPILOT_AI_TEST_PROVIDER:
        if not settings.E2E_TEST_MODE or settings.POSTGRES_DB != settings.POSTGRES_TEST_DB:
            raise SuggestionError(503, "The deterministic AI provider is restricted to guarded tests.")
        return "deterministic-test", "synthetic-v1", None
    if settings.JOBPILOT_AI_PROVIDER == "groq":
        key, model = settings.JOBPILOT_GROQ_API_KEY, settings.JOBPILOT_GROQ_MODEL
    else:
        key, model = settings.JOBPILOT_OPENAI_API_KEY, settings.JOBPILOT_AI_MODEL
    if not key or not key.strip():
        raise SuggestionError(503, "AI features are not configured.")
    return settings.JOBPILOT_AI_PROVIDER, model, key


def provider_for(settings: Settings):
    name, model, key = provider_configuration(settings)
    if name == "deterministic-test":
        return DeterministicTestProvider()
    provider_class = GroqResponsesProvider if name == "groq" else OpenAIResponsesProvider
    max_output_tokens = (
        settings.JOBPILOT_AI_MAX_OUTPUT_TOKENS
        if name == "groq"
        else settings.JOBPILOT_OPENAI_PROFILE_MAX_OUTPUT_TOKENS
    )
    return provider_class(
        api_key=key,
        model=model,
        timeout=settings.JOBPILOT_AI_TIMEOUT_SECONDS,
        max_output_tokens=max_output_tokens,
    )


def _prepare_generation(session: Session, *, owner_id: uuid.UUID, resume: Resume, settings: Settings):
    from app.services.privacy_service import require_consent
    require_consent(session, owner_id, "ai_profile_suggestions")
    extraction = session.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume.id))
    if extraction is None or extraction.status != "succeeded" or extraction.reviewed_at is None:
        raise SuggestionError(409, "Confirm the extracted CV text before requesting suggestions.")
    source = extraction.draft_text or ""
    if not source or len(source) > settings.JOBPILOT_AI_MAX_INPUT_CHARS:
        raise SuggestionError(413, "The confirmed CV text exceeds the AI input limit.")
    existing = session.scalar(select(ProfileSuggestionSet).where(
        ProfileSuggestionSet.owner_id == owner_id,
        ProfileSuggestionSet.resume_id == resume.id,
        ProfileSuggestionSet.status == "generating",
    ))
    if existing:
        raise SuggestionError(409, "Suggestions are already being generated for this resume.")
    provider_name, model, _ = provider_configuration(settings)
    from app.services import ai_usage
    try:
        token = ai_usage.reserve(session, owner_id, settings, feature="profile")
    except ai_usage.AIUsageError as error:
        raise SuggestionError(error.status_code, error.message) from None
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    record = ProfileSuggestionSet(
        owner_id=owner_id, resume_id=resume.id, extraction_id=extraction.id,
        source_text=source, source_hash=source_hash(source), source_reviewed_at=extraction.reviewed_at,
        profile_revision=profile_revision(profile), status="generating", suggestions=None,
        provider=provider_name, model=model, prompt_version=PROMPT_VERSION,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record, token


def _finish_generation(session: Session, *, record: ProfileSuggestionSet, token, settings: Settings, provider=None, background=False):
    from app.services.privacy_service import require_consent
    from app.services import ai_usage
    if provider is None:
        try:
            provider = provider_for(settings)
        except Exception:
            record.status = "failed"
            record.outcome_message = "unknown"
            ai_usage.release(session, record.owner_id, token)
            session.commit()
            if not background:
                raise
            return record
    try:
        ai_usage.dispatch_guard(session, record.owner_id)
        require_consent(session, record.owner_id, "ai_profile_suggestions")
    except Exception:
        record.status = "failed"
        record.outcome_message = "Dispatch cancelled before provider request; consent or account access changed."
        ai_usage.release(session, record.owner_id, token)
        session.commit()
        if not background:
            raise
        return record
    try:
        output = ai_usage.bounded_call(lambda: provider.suggest(record.source_text), settings.JOBPILOT_AI_TIMEOUT_SECONDS)
        suggestions, partial = validate_output(output, record.source_text)
        suggestions.extend({
            "id": f"not-found:{field}", "field": field, "status": "not_found",
            "value": None, "evidence": [],
        } for field in output.not_found)
        record.status = "ready"
        record.suggestions = suggestions
        record.outcome_message = output.message or ("Some unsupported suggestions were removed." if partial else None)
    except ProviderFailure as error:
        record.status = "failed"
        record.outcome_message = error.category
        record.failure_field = error.field
        record.failure_diagnostic = error.diagnostic
    except Exception:
        record.status = "failed"
        record.outcome_message = "unknown"
    ai_usage.release(session, record.owner_id, token)
    session.commit()
    session.refresh(record)
    return record


def _run_queued(record_id: uuid.UUID, token, settings: Settings) -> None:
    session = SessionLocal()
    try:
        record = session.get(ProfileSuggestionSet, record_id)
        if record is not None and record.status == "generating":
            _finish_generation(session, record=record, token=token, settings=settings, background=True)
    finally:
        session.close()


def queue_generation(session: Session, *, owner_id: uuid.UUID, resume: Resume, settings: Settings) -> ProfileSuggestionSet:
    record, token = _prepare_generation(session, owner_id=owner_id, resume=resume, settings=settings)
    try:
        _PROFILE_EXECUTOR.submit(_run_queued, record.id, token, settings)
    except Exception:
        from app.services import ai_usage
        record.status = "failed"
        record.outcome_message = "unknown"
        ai_usage.release(session, owner_id, token)
        session.commit()
        raise SuggestionError(503, "Could not queue profile suggestions.") from None
    return record


def validate_output(output: ProviderSuggestionOutput, source: str) -> tuple[list[dict], bool]:
    from app.services.evidence_validation import normalize, supported_claim, value_text
    accepted: list[dict] = []
    partial = output.partial
    seen: set[str] = set()
    for suggestion in output.suggestions:
        quotes = [e.quote for e in suggestion.evidence]
        if suggestion.field == "languages":
            proficiency = re.escape(suggestion.value.proficiency.replace("_", " "))
            if not re.search(rf"\b{proficiency}\b", normalize(" ".join(quotes))):
                partial = True
                continue
        if suggestion.field == "location" and _is_contact_details(str(suggestion.value)):
            partial = True
            continue
        if suggestion.field == "skills":
            if not suggestion.value:
                partial = True
                continue
            if any(_is_contact_details(skill) for skill in suggestion.value):
                partial = True
                continue
        if (suggestion.id in seen or any(e.quote not in source for e in suggestion.evidence)
                or not supported_claim(value_text(suggestion.value), quotes,
                                       single_passage=suggestion.field in {"experience", "education"})):
            partial = True
            continue
        try:
            value = (
                [suggestion.value]
                if suggestion.field in {"target_roles", "experience", "education", "languages"}
                else suggestion.value
            )
            CandidateProfileUpdate.model_validate({suggestion.field: value})
        except Exception:
            partial = True
            continue
        seen.add(suggestion.id)
        accepted.append(suggestion.model_dump(mode="json"))
    return accepted, partial


def generate(session: Session, *, owner_id: uuid.UUID, resume: Resume, settings: Settings) -> ProfileSuggestionSet:
    record, token = _prepare_generation(session, owner_id=owner_id, resume=resume, settings=settings)
    provider = provider_for(settings)
    return _finish_generation(session, record=record, token=token, settings=settings, provider=provider)


def get_owned(session: Session, *, owner_id: uuid.UUID, suggestion_id: uuid.UUID) -> ProfileSuggestionSet | None:
    return session.scalar(select(ProfileSuggestionSet).where(
        ProfileSuggestionSet.id == suggestion_id, ProfileSuggestionSet.owner_id == owner_id
    ))


def latest_for_resume(session: Session, *, owner_id: uuid.UUID, resume_id: uuid.UUID):
    return session.scalar(
        select(ProfileSuggestionSet)
        .where(ProfileSuggestionSet.owner_id == owner_id, ProfileSuggestionSet.resume_id == resume_id)
        .order_by(ProfileSuggestionSet.created_at.desc(), ProfileSuggestionSet.id.desc())
        .limit(1)
    )


def _key(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).casefold()


def apply(session: Session, *, record: ProfileSuggestionSet, selections: list[ProfileSuggestion]) -> ProfileSuggestionSet:
    selection_hash = source_hash(json.dumps([s.model_dump(mode="json") for s in selections], sort_keys=True))
    if record.applied_at:
        if record.applied_selection_hash == selection_hash:
            return record
        raise SuggestionError(409, "This suggestion set was already applied with different selections.")
    extraction = session.scalar(select(ResumeExtraction).where(ResumeExtraction.id == record.extraction_id))
    if extraction is None or extraction.reviewed_at != record.source_reviewed_at or source_hash(extraction.draft_text or "") != record.source_hash:
        raise SuggestionError(409, "The confirmed CV text changed. Generate fresh suggestions.")
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == record.owner_id).with_for_update())
    if profile_revision(profile) != record.profile_revision:
        raise SuggestionError(409, "The profile changed. Refresh and review the suggestions again.")
    offered = {
        item["id"] for item in (record.suggestions or [])
        if item.get("status") != "not_found"
    }
    if any(item.id not in offered for item in selections):
        raise SuggestionError(422, "A selected suggestion is not part of this suggestion set.")
    valid, partial = validate_output(ProviderSuggestionOutput(suggestions=selections), record.source_text)
    if partial or len(valid) != len(selections):
        raise SuggestionError(422, "A selected value is invalid or lacks source evidence.")
    profile_fields = CandidateProfileUpdate.model_fields
    current = CandidateProfileUpdate.model_validate(
        {name: getattr(profile, name) for name in profile_fields} if profile else {}
    ).model_dump(mode="json")
    applied: list[dict] = []
    for item in valid:
        field, value = item["field"], item["value"]
        if field in {"headline", "location", "remote_preference", "work_authorization", "salary_preference"}:
            current[field] = value
        else:
            values = current.get(field) or []
            if field == "skills":
                existing = {_key(skill) for skill in values}
                for skill in value:
                    if _key(skill) not in existing:
                        existing.add(_key(skill))
                        values.append(skill)
            elif _key(value) not in {_key(existing) for existing in values}:
                values.append(value)
            current[field] = values
        applied.append(item)
    final = CandidateProfileUpdate.model_validate(current)
    if profile is None:
        profile = CandidateProfile(owner_id=record.owner_id)
        session.add(profile)
    provenance = dict(profile.ai_provenance or {})
    for field, value in final.model_dump(mode="json").items():
        setattr(profile, field, value)
    for item in applied:
        entry = {
            "origin": "ai",
            "source_resume_id": str(record.resume_id),
            "source_available": True,
            "suggestion_id": item["id"],
            "value": item["value"],
            "evidence": item["evidence"],
        }
        if item["field"] in {"target_roles", "skills", "experience", "education", "languages"}:
            existing_provenance = provenance.get(item["field"])
            entries = existing_provenance if isinstance(existing_provenance, list) else []
            provenance[item["field"]] = [*entries, entry]
        else:
            provenance[item["field"]] = entry
    profile.ai_provenance = provenance
    session.flush()
    record.status = "applied"
    record.applied_at = datetime.now(timezone.utc)
    record.applied_selection_hash = selection_hash
    record.apply_result = {"applied": applied, "profile_id": str(profile.id)}
    session.commit()
    session.refresh(record)
    return record


def mark_source_unavailable(session: Session, *, owner_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    if profile is None or not profile.ai_provenance:
        return
    changed = False
    provenance = dict(profile.ai_provenance)
    for field, item in provenance.items():
        if isinstance(item, list):
            next_items = []
            for entry in item:
                if isinstance(entry, dict) and entry.get("source_resume_id") == str(resume_id):
                    next_items.append({
                        "origin": "ai", "source_resume_id": str(resume_id),
                        "source_available": False, "value": entry.get("value"),
                    })
                    changed = True
                else:
                    next_items.append(entry)
            provenance[field] = next_items
            continue
        if isinstance(item, dict) and item.get("source_resume_id") == str(resume_id):
            provenance[field] = {
                "origin": "ai",
                "source_resume_id": str(resume_id),
                "source_available": False,
                "value": item.get("value"),
            }
            changed = True
    if changed:
        profile.ai_provenance = provenance
