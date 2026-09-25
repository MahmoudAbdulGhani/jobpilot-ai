import hashlib
import json
import logging
import re
import uuid
from concurrent.futures import CancelledError, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.config import Settings
from app.models import (
    CandidateProfile, ProfileSuggestionSet, Resume, ResumeExtraction,
    UsageReservation, User,
)
from app.schemas.profile import CandidateProfileUpdate
from app.schemas.profile_suggestions import ProfileSuggestion, ProviderSuggestionOutput
from app.services.ai_provider import (
    DeterministicTestProvider,
    OpenAIResponsesProvider,
    GroqResponsesProvider,
    PROMPT_VERSION,
    ProviderFailure,
    _timeout_diagnostic,
)
from app.core.db import SessionLocal


_PROFILE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="profile-suggestions")
_PROFILE_JOB_GRACE_SECONDS = 10
_operations = logging.getLogger("jobpilot.operations")


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


def _worker_event(stage: str, outcome: str) -> None:
    # Operational lifecycle only: never include identifiers, source text,
    # provider responses, credentials, URLs, or exception strings.
    _operations.info("profile_suggestion_worker stage=%s outcome=%s", stage, outcome)


def _release_stale_profile_reservations(
    session: Session, *, record: ProfileSuggestionSet
) -> None:
    from app.services import ai_usage

    cutoff = record.created_at + timedelta(seconds=1)
    reservations = list(session.scalars(select(UsageReservation).where(
        UsageReservation.owner_id == record.owner_id,
        UsageReservation.feature == "profile",
        UsageReservation.released_at.is_(None),
        UsageReservation.created_at <= cutoff,
    )))
    for reservation in reservations:
        ai_usage.release(session, record.owner_id, reservation.id)


def _recover_stale_generation(
    session: Session, *, record: ProfileSuggestionSet, settings: Settings,
    now: datetime | None = None,
) -> bool:
    if record.status != "generating":
        return False
    current_time = now or datetime.now(timezone.utc)
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    elapsed = max(0.0, (current_time - created_at).total_seconds())
    stale_after = settings.JOBPILOT_AI_TIMEOUT_SECONDS + _PROFILE_JOB_GRACE_SECONDS
    if elapsed <= stale_after:
        return False
    diagnostic = _timeout_diagnostic(
        "outer", settings.JOBPILOT_AI_TIMEOUT_SECONDS, elapsed
    )
    diagnostic["request_stage"] = "background_worker"
    record.status = "failed"
    record.outcome_message = "timeout"
    record.failure_diagnostic = diagnostic
    _release_stale_profile_reservations(session, record=record)
    session.commit()
    session.refresh(record)
    _worker_event("stale_recovery", "failed_timeout")
    return True


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
    ).with_for_update())
    if existing:
        if not _recover_stale_generation(
            session, record=existing, settings=settings
        ):
            raise SuggestionError(409, "Suggestions are already being generated for this resume.")
    provider_name, model, _ = provider_configuration(settings)
    from app.services import ai_usage, profile_generation_quota
    try:
        token = profile_generation_quota.reserve(session, owner_id, source_hash(source), settings)
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
        _worker_event("provider", "started")
        output = ai_usage.bounded_call(lambda: provider.suggest(record.source_text), settings.JOBPILOT_AI_TIMEOUT_SECONDS)
        session.refresh(record)
        if record.status != "generating":
            ai_usage.release(session, record.owner_id, token)
            session.commit()
            _worker_event("provider", "discarded_after_recovery")
            return record
        suggestions, partial = validate_output(output, record.source_text, salvage_experience=True)
        from app.services.evidence_validation import (
            experience_section, experience_role_blocks, supported_experience,
        )
        work_text = experience_section(record.source_text)
        work_blocks = experience_role_blocks(record.source_text)
        visible_work_roles = bool(work_blocks)

        def role_index(item):
            quotes = [evidence["quote"] for evidence in item["evidence"]]
            return next((index for index, block in enumerate(work_blocks)
                         if quotes and supported_experience(
                             item["value"], quotes, "PROFESSIONAL EXPERIENCE\n" + block,
                         )), None)

        covered_roles = {index for item in suggestions if item["field"] == "experience"
                         if (index := role_index(item)) is not None}
        if work_text and (not work_blocks or len(covered_roles) < len(work_blocks)):
            # One focused retry belongs to this explicit generation request.
            try:
                suggest_experience = getattr(provider, "suggest_experience", provider.suggest)
                focused = ai_usage.bounded_call(
                    lambda: suggest_experience("PROFESSIONAL EXPERIENCE\n" + work_text),
                    settings.JOBPILOT_AI_TIMEOUT_SECONDS,
                )
                recovered, rejected = validate_output(
                    ProviderSuggestionOutput(suggestions=[item for item in focused.suggestions if item.field == "experience"]),
                    record.source_text,
                    salvage_experience=True,
                )
                for item in recovered:
                    index = role_index(item)
                    if item["field"] != "experience" or index is None or index in covered_roles:
                        continue
                    item["id"] = f"experience-recovered-{index + 1}"
                    suggestions.append(item)
                    covered_roles.add(index)
                partial = partial or rejected
            except Exception:
                partial = True
                _worker_event("experience_retry", "failed")
        suggestions.extend({
            "id": f"not-found:{field}", "field": field, "status": "not_found",
            "value": None, "evidence": [],
        } for field in output.not_found
            if not any(item["field"] == field for item in suggestions)
            and not (field == "experience" and visible_work_roles))
        record.status = "ready"
        record.suggestions = suggestions
        if work_blocks and len(covered_roles) < len(work_blocks):
            record.outcome_message = "Some CV work roles need manual review."
        else:
            record.outcome_message = output.message or ("Some unsupported suggestions were removed." if partial else None)
    except ProviderFailure as error:
        record.status = "failed"
        record.outcome_message = error.category
        record.failure_field = error.field
        record.failure_diagnostic = error.diagnostic
        _worker_event("provider", "failed")
    except Exception:
        record.status = "failed"
        record.outcome_message = "unknown"
        _worker_event("provider", "exception")
    ai_usage.release(session, record.owner_id, token)
    session.commit()
    session.refresh(record)
    if record.status == "ready":
        _worker_event("commit", "ready")
    return record


def _persist_worker_exception(record_id: uuid.UUID, token, settings: Settings) -> None:
    from app.services import ai_usage

    recovery = SessionLocal()
    try:
        record = recovery.get(ProfileSuggestionSet, record_id)
        reservation = recovery.get(UsageReservation, token)
        if record is not None and record.status == "generating":
            record.status = "failed"
            record.outcome_message = "unknown"
            record.failure_diagnostic = {
                "request_stage": "background_worker",
                "configured_timeout_seconds": settings.JOBPILOT_AI_TIMEOUT_SECONDS,
                "elapsed_time_bucket": "unknown",
                "http_status": None,
            }
        owner_id = record.owner_id if record is not None else (
            reservation.owner_id if reservation is not None else None
        )
        if owner_id is not None:
            ai_usage.release(recovery, owner_id, token)
        recovery.commit()
        _worker_event("exception_recovery", "committed")
    except Exception:
        recovery.rollback()
        _worker_event("exception_recovery", "failed")
    finally:
        recovery.close()


def _run_queued(record_id: uuid.UUID, token, settings: Settings) -> None:
    session = None
    try:
        _worker_event("worker", "started")
        session = SessionLocal()
        record = session.get(ProfileSuggestionSet, record_id)
        if record is not None and record.status == "generating":
            _finish_generation(session, record=record, token=token, settings=settings, background=True)
    except Exception:
        if session is not None:
            session.rollback()
        _worker_event("worker", "exception")
        _persist_worker_exception(record_id, token, settings)
    finally:
        if session is not None:
            session.close()


def _observe_queued(future) -> None:
    try:
        error = future.exception()
    except CancelledError:
        _worker_event("executor", "cancelled")
        return
    except Exception:
        _worker_event("executor", "observer_exception")
        return
    _worker_event("executor", "exception" if error is not None else "completed")


def queue_generation(session: Session, *, owner_id: uuid.UUID, resume: Resume, settings: Settings) -> ProfileSuggestionSet:
    record, token = _prepare_generation(session, owner_id=owner_id, resume=resume, settings=settings)
    try:
        future = _PROFILE_EXECUTOR.submit(_run_queued, record.id, token, settings)
        if hasattr(future, "add_done_callback"):
            future.add_done_callback(_observe_queued)
        _worker_event("executor", "queued")
    except Exception:
        from app.services import ai_usage
        record.status = "failed"
        record.outcome_message = "unknown"
        ai_usage.release(session, owner_id, token)
        session.commit()
        raise SuggestionError(503, "Could not queue profile suggestions.") from None
    return record


def validate_output(output: ProviderSuggestionOutput, source: str, *, salvage_experience=False) -> tuple[list[dict], bool]:
    from app.services.evidence_validation import (
        complete_experience_notes, normalize, supported_claim,
        supported_experience, value_text,
    )
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
        supported = (supported_experience(suggestion.value, quotes, source)
                     if suggestion.field == "experience" else
                     supported_claim(value_text(suggestion.value), quotes,
                                     single_passage=suggestion.field == "education"))
        if salvage_experience and suggestion.field == "experience" and not supported:
            # Keep the cited role header if generated duty notes or a date were
            # unsupported. Review/Apply never truncate a user's edited value.
            for updates in ({"notes": None}, {"notes": None, "period": None}):
                candidate = suggestion.value.model_copy(update=updates)
                header = next((quote for quote in quotes
                               if quote in source and supported_experience(candidate, [quote], source)), None)
                if header:
                    suggestion = suggestion.model_copy(update={
                        "value": candidate,
                        "evidence": [next(e for e in suggestion.evidence if e.quote == header)],
                    })
                    quotes = [header]
                    supported = True
                    partial = True
                    break
        if (suggestion.id in seen or any(e.quote not in source for e in suggestion.evidence)
                or not supported):
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
        saved = suggestion.model_dump(mode="json")
        if salvage_experience and suggestion.field == "experience":
            saved["value"], completed_quotes, incomplete = complete_experience_notes(
                saved["value"], quotes, source,
            )
            saved["evidence"] = [{"quote": quote} for quote in completed_quotes]
            partial = partial or incomplete
        accepted.append(saved)
    return accepted, partial


def generate(session: Session, *, owner_id: uuid.UUID, resume: Resume, settings: Settings) -> ProfileSuggestionSet:
    record, token = _prepare_generation(session, owner_id=owner_id, resume=resume, settings=settings)
    provider = provider_for(settings)
    return _finish_generation(session, record=record, token=token, settings=settings, provider=provider)


def get_owned(session: Session, *, owner_id: uuid.UUID, suggestion_id: uuid.UUID) -> ProfileSuggestionSet | None:
    return session.scalar(select(ProfileSuggestionSet).where(
        ProfileSuggestionSet.id == suggestion_id, ProfileSuggestionSet.owner_id == owner_id
    ))


def latest_for_resume(
    session: Session, *, owner_id: uuid.UUID, resume_id: uuid.UUID,
    settings: Settings | None = None,
):
    record = session.scalar(
        select(ProfileSuggestionSet)
        .where(ProfileSuggestionSet.owner_id == owner_id, ProfileSuggestionSet.resume_id == resume_id)
        .order_by(ProfileSuggestionSet.created_at.desc(), ProfileSuggestionSet.id.desc())
        .limit(1)
        .with_for_update()
    )
    if record is not None and settings is not None:
        _recover_stale_generation(session, record=record, settings=settings)
    return record


def _key(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).casefold()


def _check_source(session: Session, record: ProfileSuggestionSet, *, lock=False):
    query = select(ResumeExtraction).where(ResumeExtraction.id == record.extraction_id)
    if lock:
        query = query.with_for_update()
    extraction = session.scalar(query.execution_options(populate_existing=True))
    if extraction is None or extraction.reviewed_at != record.source_reviewed_at or source_hash(extraction.draft_text or "") != record.source_hash:
        raise SuggestionError(409, "The confirmed CV text changed. Generate fresh suggestions.")


def _merge_changes(record, profile, selections, manual_fields, manual_experience_entries=()):
    manual = manual_fields.model_dump(mode="json", exclude_unset=True) if manual_fields else {}
    additions = [item.model_dump(mode="json") for item in manual_experience_entries]
    if not selections and not manual and not additions:
        raise SuggestionError(422, "Select at least one suggestion or edit a manual field.")
    if additions and "experience" in manual:
        raise SuggestionError(422, "experience: choose either a replacement list or added experience entries.")
    overlap = set(manual) & {item.field for item in selections}
    if overlap:
        raise SuggestionError(422, f"{', '.join(sorted(overlap))}: choose either AI suggestions or manual changes for this field.")
    offered = {
        item["id"]: item["field"] for item in (record.suggestions or [])
        if item.get("status") != "not_found"
    }
    if any(offered.get(item.id) != item.field for item in selections):
        raise SuggestionError(422, "A selected suggestion is not part of this suggestion set or its field changed.")
    valid, partial = validate_output(ProviderSuggestionOutput(suggestions=selections), record.source_text)
    if partial or len(valid) != len(selections):
        accepted = {item["id"] for item in valid}
        fields = sorted({item.field for item in selections if item.id not in accepted})
        raise SuggestionError(422, f"{', '.join(fields) or 'selections'}: A selected value is invalid or lacks source evidence.")
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
    accepted_additions = []
    if additions:
        entries = current.get("experience") or []
        seen_entries = {_key(entry) for entry in entries}
        for entry in additions:
            if _key(entry) not in seen_entries:
                entries.append(entry)
                accepted_additions.append(entry)
                seen_entries.add(_key(entry))
        current["experience"] = entries
    current.update(manual)
    try:
        final = CandidateProfileUpdate.model_validate(current)
    except ValidationError as error:
        messages = [f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                    for item in error.errors(include_input=False)]
        raise SuggestionError(422, "; ".join(messages)) from error
    return final, applied, manual, accepted_additions


def review(session: Session, *, record: ProfileSuggestionSet, selections, manual_fields=None,
           manual_experience_entries=()):
    if record.status != "ready" or record.applied_at:
        raise SuggestionError(409, "This suggestion set is not available for review.")
    _check_source(session, record)
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == record.owner_id))
    final, applied, manual, additions = _merge_changes(record, profile, selections, manual_fields, manual_experience_entries)
    return {
        "current_profile": profile,
        "proposed_profile": final,
        "reviewed_profile_revision": profile_revision(profile),
        "changed_fields": sorted({item["field"] for item in applied} | set(manual) | ({"experience"} if additions else set())),
    }


def apply(session: Session, *, record: ProfileSuggestionSet, selections: list[ProfileSuggestion],
          manual_fields: CandidateProfileUpdate | None = None,
          manual_experience_entries=(),
          reviewed_profile_revision: str | None = None) -> ProfileSuggestionSet:
    # Serialize profile writes even when the profile does not exist yet.
    session.scalar(select(User.id).where(User.id == record.owner_id).with_for_update())
    record = session.scalar(select(ProfileSuggestionSet).where(ProfileSuggestionSet.id == record.id)
                            .with_for_update().execution_options(populate_existing=True))
    if record is None:
        raise SuggestionError(404, "Suggestion set not found")
    manual = manual_fields.model_dump(mode="json", exclude_unset=True) if manual_fields else {}
    additions_input = [item.model_dump(mode="json") for item in manual_experience_entries]
    serialized = [s.model_dump(mode="json") for s in selections]
    # Preserve legacy hashes when no manual fields were submitted.
    hash_input = ({"selections": serialized, "manual_fields": manual,
                   "manual_experience_entries": additions_input} if additions_input else
                  {"selections": serialized, "manual_fields": manual} if manual else serialized)
    selection_hash = source_hash(json.dumps(hash_input, sort_keys=True))
    if record.applied_at:
        if record.applied_selection_hash == selection_hash:
            return record
        raise SuggestionError(409, "This suggestion set was already applied with different selections.")
    if record.status != "ready":
        raise SuggestionError(409, "This suggestion set is not ready to save.")
    _check_source(session, record, lock=True)
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == record.owner_id)
                             .with_for_update().execution_options(populate_existing=True))
    expected = reviewed_profile_revision if reviewed_profile_revision is not None else record.profile_revision
    if profile_revision(profile) != expected:
        raise SuggestionError(409, "The profile changed. Review profile changes again before saving.")
    final, applied, manual, additions = _merge_changes(record, profile, selections, manual_fields, manual_experience_entries)
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
    for field in manual:
        provenance[field] = {"origin": "user"}
    if additions:
        entries = provenance.get("experience")
        entries = entries if isinstance(entries, list) else []
        provenance["experience"] = [*entries, *({"origin": "user", "value": entry} for entry in additions)]
    profile.ai_provenance = provenance
    session.flush()
    record.status = "applied"
    record.applied_at = datetime.now(timezone.utc)
    record.applied_selection_hash = selection_hash
    record.apply_result = {"applied": applied, "manual_fields": manual,
                           "manual_experience_entries": additions, "profile_id": str(profile.id),
                           "reviewed_profile_revision": expected}
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
