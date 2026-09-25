"""Owner-scoped immutable source snapshots and append-only document revisions."""
import copy
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from sqlalchemy import func, select, update

from app.models import ApplicationPack, ApplicationPackOperation, ApplicationPackVersion, CandidateProfile, Resume, ResumeExtraction, SavedJob
from app.schemas.application_packs import (
    HEADINGS,
    PackGenerate,
    PackList,
    PackOptions,
    PackOperation,
    PackProviderOutput,
    PackResponse,
    PackVersionList,
    PackVersionResponse,
)
from app.schemas.profile import CandidateProfileUpdate
from app.services import ai_usage
from app.services.ai_provider import ProviderFailure, OpenAIResponsesProvider, DeterministicTestProvider, PACK_PROMPT_VERSION
from app.services.profile_suggestion_service import SuggestionError, provider_configuration as shared_provider_configuration

PROMPT_VERSION = PACK_PROMPT_VERSION
MAX_VERSIONS = 100


class PackError(Exception):
    def __init__(self, status_code, message):
        self.status_code, self.message = status_code, message
        super().__init__(message)


def pack_failure_message(error: ProviderFailure) -> str:
    """Only provider failure categories, never upstream text, reach saved packs."""
    messages = {
        "output_limit": "The AI response reached the pack output limit before both documents were complete. No draft was saved.",
        "timeout": "The AI provider timed out before both documents were complete. No draft was saved.",
        "rate_limit": "The AI provider is rate limited. Try again later; no draft was saved.",
        "billing": "The AI provider account cannot process this request. Check provider billing settings.",
        "authentication": "The AI provider credential was rejected. Check the deployment secret.",
        "model_unavailable": "The configured AI model is unavailable for application packs.",
        "invalid_request": "The AI provider rejected the pack request. No draft was saved.",
        "request_contract_invalid": "The AI provider rejected the pack response schema. No draft was saved.",
        "structured_output_invalid": "The AI provider did not return a complete structured pack. No draft was saved.",
    }
    return messages.get(error.category, "The AI provider could not produce a complete supported draft. No draft was saved.")


def pack_provider_configuration(settings):
    # Reuse enablement, credential and guarded-test gates; never fall back to
    # the profile/fit provider when pack credentials are absent.
    return shared_provider_configuration(settings.model_copy(update={
        "JOBPILOT_AI_PROVIDER": settings.JOBPILOT_PACK_PROVIDER,
        "JOBPILOT_AI_MODEL": settings.JOBPILOT_PACK_MODEL,
    }))


def pack_provider_for(settings):
    name, model, key = pack_provider_configuration(settings)
    if name == "deterministic-test":
        return DeterministicTestProvider()
    return OpenAIResponsesProvider(
        api_key=key, model=model, timeout=settings.JOBPILOT_PACK_TIMEOUT_SECONDS,
        max_output_tokens=settings.JOBPILOT_PACK_MAX_OUTPUT_TOKENS,
        pack_reasoning_effort=settings.JOBPILOT_PACK_REASONING_EFFORT,
    )


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def owned_job(db, owner_id, job_id, lock=False):
    query = select(SavedJob).where(SavedJob.id == job_id, SavedJob.owner_id ==
                                   owner_id).execution_options(populate_existing=True)
    job = db.scalar(query.with_for_update() if lock else query)
    if job is None:
        raise PackError(404, "Job not found")
    return job


def capture(db, owner_id, job_id, resume_id, lock=False):
    job = owned_job(db, owner_id, job_id, lock)
    query = select(Resume).where(Resume.id == resume_id, Resume.owner_id ==
                                 owner_id).execution_options(populate_existing=True)
    resume = db.scalar(query.with_for_update() if lock else query)
    if resume is None:
        raise PackError(404, "Resume not found")
    query = select(CandidateProfile).where(
        CandidateProfile.owner_id == owner_id).execution_options(populate_existing=True)
    profile = db.scalar(query.with_for_update() if lock else query)
    query = select(ResumeExtraction).where(ResumeExtraction.resume_id ==
                                           resume.id).execution_options(populate_existing=True)
    extraction = db.scalar(query.with_for_update() if lock else query)
    if not (job.description or "").strip():
        raise PackError(
            409, "Save a job description before generating an application pack.")
    if profile is None:
        raise PackError(
            409, "Save your candidate profile before generating an application pack.")
    values = CandidateProfileUpdate.model_validate({name: getattr(
        profile, name) for name in CandidateProfileUpdate.model_fields}).model_dump(mode="json")
    if not any(value for value in values.values()):
        raise PackError(
            409, "Add candidate facts to your saved profile first.")
    if extraction is None or extraction.status != "succeeded" or extraction.reviewed_at is None or not (extraction.draft_text or "").strip():
        raise PackError(
            409, "Select a CV with nonempty confirmed text from the resume library.")
    facts = []
    # Keep each experience/project context intact; no silent truncation of notes.
    for path, value in values.items():
        for index, item in enumerate(value if isinstance(value, list) else [value]):
            if not item:
                continue
            facts.append({"id": f"fact-{len(facts) + 1}", "path": f"{path}[{index}]" if isinstance(value, list) else path,
                          "value": json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)})
    snapshot = {
        "job": {"id": str(job.id), "title": job.title, "company": job.company, "location": job.location, "description": job.description},
        "profile_id": str(profile.id), "profile": values, "profile_facts": facts,
        "resume_id": str(resume.id), "extraction_id": str(extraction.id), "cv_text": extraction.draft_text,
        "resume_name": resume.display_name, "reviewed_at": extraction.reviewed_at.isoformat(),
        "job_updated_at": job.updated_at.isoformat(), "profile_updated_at": profile.updated_at.isoformat(),
    }
    return snapshot


def source_hash(snapshot):
    # Display names and timestamps/notes/archive are not candidate facts.
    return digest({key: snapshot[key] for key in ("job", "profile_id", "profile", "resume_id", "extraction_id", "cv_text")})


def outdated(db, pack):
    try:
        return source_hash(capture(db, pack.owner_id, pack.job_id, pack.resume_id)) != pack.source_hash
    except PackError:
        return True


def get_owned(db, owner_id, job_id, pack_id, lock=False):
    owned_job(db, owner_id, job_id)
    query = select(ApplicationPack).where(ApplicationPack.id == pack_id, ApplicationPack.owner_id ==
                                          owner_id, ApplicationPack.job_id == job_id).execution_options(populate_existing=True)
    pack = db.scalar(query.with_for_update() if lock else query)
    if pack is None:
        raise PackError(404, "Application pack not found")
    return pack


def version_for(db, pack, number):
    version = db.scalar(select(ApplicationPackVersion).where(ApplicationPackVersion.pack_id ==
                        pack.id, ApplicationPackVersion.number == number).execution_options(populate_existing=True))
    if version is None:
        raise PackError(404, "Application pack version not found")
    return version


def response(db, pack, version=None):
    status, message = pack.status, pack.outcome_message
    if status == "generating" and pack.deadline < datetime.now(timezone.utc):
        status, message = "failed", "Generation expired. Generate a new pack to retry."
    return PackResponse(
        id=pack.id, job_id=pack.job_id, resume_id=pack.resume_id, status=status, current_version=pack.current_version,
        version=PackVersionResponse.model_validate(version or version_for(
            db, pack, pack.current_version)) if pack.current_version else None,
        review_notes=pack.review_notes, source_snapshot=pack.source_snapshot, is_outdated=outdated(
            db, pack),
        provider=pack.provider, model=pack.model, outcome_message=message, created_at=pack.created_at,
    )


def canonical_structural_labels(output: PackProviderOutput, snapshot):
    """Canonicalize only known labels; never guess from length or factual prose.

    Work on a copy so raw provider evidence remains available for diagnostics.
    Revalidate after removing a redundant label: headings alone are not a document.
    """
    payload = output.model_dump(mode="json")
    for block in payload["cv"]["blocks"]:
        if block["kind"] == "paragraph" and block["text"] == "Contact" and not block["evidence"]:
            block["kind"] = "heading"
    letter = payload["cover_letter"]["blocks"]
    title = snapshot.get("job", {}).get("title")
    if isinstance(title, str) and title and any(
        block["kind"] == "heading" and block["text"] == "Cover letter" for block in letter
    ):
        # Exact saved-job context only, redundant with the document heading.
        # No prefix matching, whitespace folding, inferred titles or appended claims.
        payload["cover_letter"]["blocks"] = [block for block in letter if not (
            block["kind"] == "paragraph" and not block["evidence"]
            and block["text"] == "Application for " + title
        )]
    return PackProviderOutput.model_validate(payload)


def validate_generated(output, snapshot):
    from app.services.evidence_validation import supported_claim
    output = canonical_structural_labels(PackProviderOutput.model_validate(output), snapshot)
    facts = {fact["id"]: fact["value"] for fact in snapshot["profile_facts"]}
    for document in (output.cv, output.cover_letter):
        for block in document.blocks:
            if block.kind == "heading" and block.text not in HEADINGS:
                raise PackError(
                    502, "The generated document included an unsupported heading. Retry generation.")
            if block.kind != "heading" and not block.evidence:
                raise PackError(
                    502, "A generated claim was missing source evidence. Retry generation.")
            for evidence in block.evidence:
                if not evidence.fact_id and not (evidence.cv_quote or "").strip():
                    raise PackError(
                        502, "The generated document included empty evidence.")
                if evidence.fact_id and evidence.fact_id not in facts:
                    raise PackError(
                        502, "The generated document referenced an unknown profile fact.")
                if evidence.cv_quote is not None and (not evidence.cv_quote.strip() or evidence.cv_quote not in snapshot["cv_text"]):
                    raise PackError(
                        502, "The generated document included an unsupported CV passage.")
            if block.kind != "heading":
                passages = [passage for e in block.evidence
                            for passage in (facts.get(e.fact_id), e.cv_quote) if passage]
                if not supported_claim(block.text, passages):
                    raise PackError(502, "The draft contains a claim not supported by its cited evidence. Review the source and try again.")
    return output


def store_generated(document):
    return {"blocks": [{**block.model_dump(mode="json"), "origin": "ai"} for block in document.blocks]}


def generate(db, owner_id, job_id, body, settings):
    from app.services.privacy_service import require_consent
    require_consent(db, owner_id, "ai_application_packs")
    snapshot = capture(db, owner_id, job_id, body.resume_id)
    hashed = source_hash(snapshot)
    # Serialize duplicate requests and shared AI usage before recording a claim.
    from app.models import User
    db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    existing = db.scalar(select(ApplicationPack).where(
        ApplicationPack.owner_id == owner_id, ApplicationPack.idempotency_key == body.idempotency_key))
    if existing:
        if existing.job_id != job_id or existing.source_hash != hashed:
            raise PackError(
                409, "This request key was used with different sources. Start a new generation.")
        return existing
    try:
        provider = pack_provider_for(settings)
    except SuggestionError as error:
        raise PackError(error.status_code, error.message) from None
    request_source = {
        "job": snapshot["job"], "profile_facts": snapshot["profile_facts"], "cv_text": snapshot["cv_text"]}
    if len(json.dumps(request_source, ensure_ascii=False)) > settings.JOBPILOT_AI_MAX_INPUT_CHARS:
        raise PackError(
            413, "The job, profile and CV text exceed the AI input limit. Use a shorter confirmed CV.")
    try:
        token = ai_usage.reserve(db, owner_id, settings.model_copy(update={
            "JOBPILOT_AI_TIMEOUT_SECONDS": settings.JOBPILOT_PACK_TIMEOUT_SECONDS,
        }), feature="pack")
    except ai_usage.AIUsageError as error:
        raise PackError(error.status_code, error.message) from None
    now = datetime.now(timezone.utc)
    db.execute(update(ApplicationPack).where(ApplicationPack.owner_id == owner_id, ApplicationPack.status == "generating",
               ApplicationPack.deadline < now).values(status="failed", outcome_message="Generation expired. Generate a new pack to retry."))
    pack_id = uuid.uuid4()
    pack = ApplicationPack(id=pack_id, owner_id=owner_id, job_id=job_id, profile_id=uuid.UUID(snapshot["profile_id"]),
                           resume_id=body.resume_id, extraction_id=uuid.UUID(
                               snapshot["extraction_id"]),
                           source_snapshot=snapshot, source_hash=hashed, idempotency_key=body.idempotency_key,
                           status="generating", current_version=0, generated=None, review_notes=[], provider=provider.name,
                           model=provider.model, prompt_version=PROMPT_VERSION, deadline=now + timedelta(seconds=settings.JOBPILOT_PACK_TIMEOUT_SECONDS + 10))
    db.add(pack)
    db.commit()
    try:
        ai_usage.dispatch_guard(db, owner_id)
        require_consent(db, owner_id, "ai_application_packs")
    except Exception:
        pack.status = "failed"
        pack.outcome_message = "Dispatch cancelled before provider request; consent or account access changed."
        ai_usage.release(db, owner_id, token)
        db.commit()
        raise
    try:
        result = ai_usage.bounded_call(lambda: provider.create_pack(
            request_source), settings.JOBPILOT_PACK_TIMEOUT_SECONDS)
        output = validate_generated(result, snapshot)
        failure = None
    except PackError as error:
        output, failure = None, error.message
    except ProviderFailure as error:
        output, failure = None, pack_failure_message(error)
    except Exception:
        output, failure = None, "The AI provider could not produce a complete supported draft. Retry generation."
    try:
        pack = get_owned(db, owner_id, job_id, pack_id, lock=True)
    except PackError:
        ai_usage.release(db, owner_id, token)
        db.commit()
        raise PackError(404, "Application pack no longer exists") from None
    ai_usage.release(db, owner_id, token)
    if pack.status != "generating" or pack.deadline < datetime.now(timezone.utc):
        db.commit()
        raise PackError(
            409, "Generation expired. Generate a new pack to retry.")
    if failure:
        pack.status, pack.outcome_message = "failed", failure
    else:
        pack.generated = output.model_dump(mode="json")
        pack.review_notes = [
            "Human review is required: valid references do not prove a claim is correct. Compare contacts, projects and dates with the captured CV.", *output.review_notes]
        pack.status, pack.current_version = "ready", 1
        db.add(ApplicationPackVersion(pack_id=pack.id, number=1, cv=store_generated(
            output.cv), cover_letter=store_generated(output.cover_letter)))
    db.commit()
    return get_owned(db, owner_id, job_id, pack_id)


def edited_document(incoming, previous):
    originals = {block["id"]: block for block in previous["blocks"]}
    blocks = []
    for block in incoming.blocks:
        old = originals.get(block.id)
        if old and old["kind"] == block.kind and old["text"] == block.text:
            blocks.append(copy.deepcopy(old))
        else:
            blocks.append(
                {**block.model_dump(), "origin": "user", "evidence": []})
    return {"blocks": blocks}


def edit_or_approve(db, owner_id, job_id, pack_id, body, approve=False):
    # Source rows are locked before the pack to serialize approval with source
    # edits/deletions; this uses the same order as generation capture.
    pack = get_owned(db, owner_id, job_id, pack_id)
    if approve:
        snap = capture(db, owner_id, job_id, pack.resume_id, lock=True)
    pack = get_owned(db, owner_id, job_id, pack_id, lock=True)
    payload_hash = digest(
        {"action": "approve" if approve else "save", **body.model_dump(mode="json")})
    prior = db.scalar(select(ApplicationPackOperation).where(
        ApplicationPackOperation.pack_id == pack.id, ApplicationPackOperation.key == body.idempotency_key))
    if prior:
        if prior.request_hash != payload_hash:
            raise PackError(
                409, "This request key was already used for different edits or approval.")
        return pack, version_for(db, pack, prior.version_number)
    if pack.status != "ready" or pack.current_version != body.expected_version:
        raise PackError(
            409, "This draft changed in another request. Reload it before saving or approving.")
    current = version_for(db, pack, pack.current_version)
    if approve:
        if current.approved_at is None:
            if source_hash(snap) != pack.source_hash:
                raise PackError(
                    409, "The source content changed. Generate a fresh pack before approval.")
            current.approved_at = datetime.now(timezone.utc)
    else:
        cv = edited_document(body.cv, current.cv)
        letter = edited_document(body.cover_letter, current.cover_letter)
        if cv != current.cv or letter != current.cover_letter:
            if pack.current_version >= MAX_VERSIONS:
                raise PackError(
                    409, "This pack reached its 100-version limit. Generate a new pack.")
            pack.current_version += 1
            current = ApplicationPackVersion(
                pack_id=pack.id, number=pack.current_version, cv=cv, cover_letter=letter)
            db.add(current)
    db.add(ApplicationPackOperation(pack_id=pack.id, key=body.idempotency_key,
           request_hash=payload_hash, version_number=current.number))
    db.commit()
    return pack, current


def improve_pack(db, owner_id, job_id, pack_id, *, report_id, target_version,
                 checks, readiness_score, body, settings):
    """Closed-loop improvement: a readiness report produces one new draft version.

    Only an approved version that is still current can be improved. The new
    version is never approved automatically: the owner reviews it and approves
    it through the existing per-version approval gate. Prior versions and their
    reports stay immutable. Generation reuses the same evidence contract as
    pack creation, so no claim can appear without valid source evidence.
    """
    from app.services.privacy_service import require_consent
    require_consent(db, owner_id, "ai_application_packs")
    pack = get_owned(db, owner_id, job_id, pack_id)
    if pack.status != "ready":
        raise PackError(409, "This pack is not ready to improve.")
    # Same lock ordering as approval: source rows first, then the pack.
    snap = capture(db, owner_id, job_id, pack.resume_id, lock=True)
    pack = get_owned(db, owner_id, job_id, pack_id, lock=True)
    payload_hash = digest({
        "action": "improve", "report_id": str(report_id), "target_version": target_version,
        "checks": checks, **body.model_dump(mode="json")})
    prior = db.scalar(select(ApplicationPackOperation).where(
        ApplicationPackOperation.pack_id == pack.id,
        ApplicationPackOperation.key == body.idempotency_key))
    if prior:
        if prior.request_hash != payload_hash:
            raise PackError(
                409, "This request key was already used for different edits or approval.")
        version = version_for(db, pack, prior.version_number)
        return pack, version, version.review_notes or []
    current = version_for(db, pack, target_version)
    if pack.current_version != target_version:
        raise PackError(
            409, "The approved draft is no longer current. Reload before improving.")
    if current.approved_at is None:
        raise PackError(
            409, "Approve the pack version before improving from its report.")
    if source_hash(snap) != pack.source_hash:
        raise PackError(
            409, "The source content changed. Approve a fresh pack before improving.")
    if pack.current_version >= MAX_VERSIONS:
        raise PackError(
            409, "This pack reached its 100-version limit. Generate a new pack.")
    try:
        provider = pack_provider_for(settings)
    except SuggestionError as error:
        raise PackError(error.status_code, error.message) from None
    revision = {
        "job": snap["job"],
        "cv": current.cv or {"blocks": []},
        "cover_letter": current.cover_letter or {"blocks": []},
        "checks": checks,
        "readiness_score": readiness_score,
    }
    try:
        token = ai_usage.reserve(db, owner_id, settings.model_copy(update={
            "JOBPILOT_AI_TIMEOUT_SECONDS": settings.JOBPILOT_PACK_TIMEOUT_SECONDS,
        }), feature="pack")
    except ai_usage.AIUsageError as error:
        raise PackError(error.status_code, error.message) from None
    try:
        ai_usage.dispatch_guard(db, owner_id)
        require_consent(db, owner_id, "ai_application_packs")
    except Exception:
        ai_usage.release(db, owner_id, token)
        db.commit()
        raise
    try:
        result = ai_usage.bounded_call(lambda: provider.improve_pack(revision), settings.JOBPILOT_PACK_TIMEOUT_SECONDS)
        output = validate_generated(result, snap)
        failure = None
    except PackError as error:
        output, failure = None, error.message
    except ProviderFailure as error:
        output, failure = None, pack_failure_message(error)
    except Exception:
        output, failure = None, "The AI provider could not produce a supported improved draft. Retry."
    ai_usage.release(db, owner_id, token)
    if failure:
        db.commit()
        raise PackError(502, failure)
    pack.current_version += 1
    notes = [
        "Human review is required: valid references do not prove a claim is correct. "
        "Compare the improved draft with the captured CV.", *output.review_notes]
    improved = ApplicationPackVersion(pack_id=pack.id, number=pack.current_version,
                                      cv=store_generated(output.cv),
                                      cover_letter=store_generated(output.cover_letter),
                                      review_notes=notes)
    db.add(improved)
    db.add(ApplicationPackOperation(pack_id=pack.id, key=body.idempotency_key,
           request_hash=payload_hash, version_number=improved.number))
    db.commit()
    return pack, improved, notes


def options(db, owner_id, job_id, settings):
    owned_job(db, owner_id, job_id)
    model = settings.JOBPILOT_PACK_MODEL
    try:
        provider, model, _ = pack_provider_configuration(settings)
        available = True
    except SuggestionError:
        provider, available = "unknown", False
    reason = None if available else "AI generation is unavailable in this environment."
    profile = db.scalar(select(CandidateProfile).where(
        CandidateProfile.owner_id == owner_id).execution_options(populate_existing=True))
    has_profile = profile is not None and any(
        getattr(profile, name) for name in CandidateProfileUpdate.model_fields)
    description = db.scalar(select(SavedJob.description).where(
        SavedJob.id == job_id, SavedJob.owner_id == owner_id)) or ""
    has_description = bool((description or "").strip())
    rows = db.execute(select(Resume, ResumeExtraction).outerjoin(
        ResumeExtraction, ResumeExtraction.resume_id == Resume.id).where(Resume.owner_id == owner_id)).all()
    resumes = []
    for resume, extraction in rows:
        if extraction and extraction.status == "succeeded" and extraction.reviewed_at and (extraction.draft_text or "").strip():
            resumes.append({"id": str(resume.id), "display_name": resume.display_name,
                           "reviewed_at": extraction.reviewed_at.isoformat()})
    return {"provider": provider, "model": model, "available": available, "reason": reason, "resumes": resumes, "has_profile": has_profile, "has_description": has_description}


def list_versions(db, owner_id, job_id, pack_id, page, page_size):
    get_owned(db, owner_id, job_id, pack_id)
    query = select(ApplicationPackVersion).where(
        ApplicationPackVersion.pack_id == pack_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(ApplicationPackVersion.number.desc(
    ), ApplicationPackVersion.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [PackVersionResponse.model_validate(item) for item in items], "total": total, "page": page, "page_size": page_size}


def get_download_version(db, owner_id, job_id, pack_id, version_number):
    pack = get_owned(db, owner_id, job_id, pack_id)
    version = version_for(db, pack, version_number)
    return pack, version


def delete_pack(db, owner_id, job_id, pack_id):
    pack = get_owned(db, owner_id, job_id, pack_id)
    db.delete(pack)
    db.commit()


def list_packs(db, owner_id, job_id, page, page_size):
    owned_job(db, owner_id, job_id)
    query = select(ApplicationPack).where(
        ApplicationPack.owner_id == owner_id, ApplicationPack.job_id == job_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(ApplicationPack.created_at.desc(
    ), ApplicationPack.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": [response(db, pack) for pack in items], "total": total, "page": page, "page_size": page_size}
