import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import CandidateProfile, ProfileSuggestionSet, Resume, ResumeExtraction
from app.schemas.profile import CandidateProfileUpdate
from app.schemas.profile_suggestions import ProfileSuggestion, ProviderSuggestionOutput
from app.services.ai_provider import (
    DeterministicTestProvider,
    OpenAIResponsesProvider,
    PROMPT_VERSION,
    ProviderFailure,
)


class SuggestionError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def profile_revision(profile: CandidateProfile | None) -> str:
    return "none" if profile is None else profile.updated_at.isoformat()


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def provider_for(settings: Settings):
    if not settings.JOBPILOT_AI_ENABLED:
        raise SuggestionError(503, "AI features are disabled.")
    if settings.JOBPILOT_AI_TEST_PROVIDER:
        if not settings.E2E_TEST_MODE or settings.POSTGRES_DB != settings.POSTGRES_TEST_DB:
            raise SuggestionError(503, "The deterministic AI provider is restricted to guarded tests.")
        return DeterministicTestProvider()
    if not settings.JOBPILOT_OPENAI_API_KEY:
        raise SuggestionError(503, "AI features are not configured.")
    return OpenAIResponsesProvider(
        api_key=settings.JOBPILOT_OPENAI_API_KEY,
        model=settings.JOBPILOT_AI_MODEL,
        timeout=settings.JOBPILOT_AI_TIMEOUT_SECONDS,
        max_output_tokens=settings.JOBPILOT_AI_MAX_OUTPUT_TOKENS,
    )


def validate_output(output: ProviderSuggestionOutput, source: str) -> tuple[list[dict], bool]:
    accepted: list[dict] = []
    partial = output.partial
    seen: set[str] = set()
    for suggestion in output.suggestions:
        if suggestion.id in seen or any(e.quote not in source for e in suggestion.evidence):
            partial = True
            continue
        try:
            value = (
                [suggestion.value]
                if suggestion.field in {"skills", "experience", "education", "languages"}
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
    count = session.scalar(select(func.count()).select_from(ProfileSuggestionSet).where(ProfileSuggestionSet.owner_id == owner_id)) or 0
    if count >= settings.JOBPILOT_AI_MAX_REQUESTS_PER_USER:
        raise SuggestionError(429, "AI suggestion usage limit reached.")
    provider = provider_for(settings)
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    record = ProfileSuggestionSet(
        owner_id=owner_id, resume_id=resume.id, extraction_id=extraction.id,
        source_text=source, source_hash=source_hash(source), source_reviewed_at=extraction.reviewed_at,
        profile_revision=profile_revision(profile), status="generating", suggestions=None,
        provider=provider.name, model=provider.model, prompt_version=PROMPT_VERSION,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    try:
        output = provider.suggest(source)
        suggestions, partial = validate_output(output, source)
        record.status = "ready"
        record.suggestions = suggestions
        record.outcome_message = output.message or ("Some unsupported suggestions were removed." if partial else None)
    except ProviderFailure as error:
        record.status = "failed"
        record.outcome_message = str(error)
    session.commit()
    session.refresh(record)
    return record


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
    offered = {item["id"] for item in (record.suggestions or [])}
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
        if field in {"headline", "location"}:
            current[field] = value
        else:
            values = current.get(field) or []
            if _key(value) not in {_key(existing) for existing in values}:
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
        if item["field"] in {"skills", "experience", "education", "languages"}:
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
