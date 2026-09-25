import hashlib
import json
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import CandidateProfile, JobFitAnalysis, SavedJob
from app.schemas.job_fit import CandidateFact, ProviderJobFitOutput
from app.services.ai_provider import JOB_FIT_PROMPT_VERSION, ProviderFailure
from app.services.profile_suggestion_service import SuggestionError, provider_for


class JobFitError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def _hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def job_snapshot(job: SavedJob) -> dict:
    return {
        "id": str(job.id), "title": job.title, "company": job.company,
        "location": job.location, "description": (job.description or "").strip(),
    }


def profile_facts(profile: CandidateProfile) -> list[CandidateFact]:
    raw: list[tuple[str, str]] = []
    for name in ("headline", "location", "remote_preference", "work_authorization"):
        value = getattr(profile, name)
        if value:
            raw.append((name, str(value)))
    for name in ("target_roles", "skills"):
        for index, value in enumerate(getattr(profile, name) or []):
            raw.append((f"{name}[{index}]", str(value)))
    for name in ("experience", "education", "languages"):
        for index, entry in enumerate(getattr(profile, name) or []):
            readable = "; ".join(f"{key}: {value}" for key, value in entry.items() if value)
            if readable:
                raw.append((f"{name}[{index}]", readable))
    salary = profile.salary_preference
    if salary:
        raw.append(("salary_preference", "; ".join(f"{key}: {value}" for key, value in salary.items() if value is not None)))
    return [CandidateFact(id=f"fact-{index + 1}", path=path, value=value[:2000]) for index, (path, value) in enumerate(raw)]


def input_state(job: SavedJob, profile: CandidateProfile) -> tuple[dict, list[CandidateFact], str, str]:
    snapshot = job_snapshot(job)
    facts = profile_facts(profile)
    return snapshot, facts, _hash(snapshot), _hash([fact.model_dump() for fact in facts])


_FIT_SECTION = re.compile(
    r"\b(basic qualifications|required qualifications|required skills|minimum qualifications|"
    r"preferred qualifications|preferred skills(?:/experience)?|nice to have|"
    r"additional qualifications|key responsibilities)\s*:", re.I)


def evidenced_importance(quote: str, description: str) -> str:
    """Classify priority from the quoted words or an unambiguous source section."""
    lowered = quote.casefold()
    if re.search(r"\b(must|required|minimum|need(?:s|ed)?|at least)\b", lowered) and not re.search(r"\bnot\s+required\b", lowered):
        return "required"
    if re.search(r"\b(preferred|preferably|bonus|nice to have)\b", lowered):
        return "preferred"
    start = description.find(quote)
    if start < 0 or description.find(quote, start + 1) >= 0:
        return "unspecified"
    sections = list(_FIT_SECTION.finditer(description, 0, start))
    if not sections or start - sections[-1].end() > 4_000:
        return "unspecified"
    heading = sections[-1].group(1).casefold()
    if heading.startswith(("basic", "required", "minimum")):
        return "required"
    if heading.startswith(("preferred", "nice to have")):
        return "preferred"
    return "unspecified"


def validate_output(output: ProviderJobFitOutput, description: str, facts: list[CandidateFact]) -> dict:
    fact_ids = {fact.id for fact in facts}
    result = output.model_dump(mode="json", exclude={"missing_skills"})
    for requirement, saved in zip(output.requirements, result["requirements"]):
        refs = set(requirement.candidate_fact_ids)
        if requirement.job_quote not in description:
            raise JobFitError(502, "The AI response contained unsupported job evidence.")
        if requirement.skill_name and requirement.skill_name.casefold() not in requirement.job_quote.casefold():
            raise JobFitError(502, "The AI response named a skill absent from the quoted requirement.")
        if not refs <= fact_ids:
            raise JobFitError(502, "The AI response referenced unknown candidate evidence.")
        if requirement.assessment in {"supported", "partially_supported", "explicit_mismatch"} and not refs:
            raise JobFitError(502, "The AI response lacked required candidate evidence.")
        if requirement.assessment == "not_evidenced" and refs:
            raise JobFitError(502, "The AI response used incompatible evidence for a missing-information assessment.")
        saved["importance"] = evidenced_importance(requirement.job_quote, description)
    return result


def counts(result: dict | None) -> dict[str, int]:
    values = {name: 0 for name in ("supported", "partially_supported", "not_evidenced", "needs_clarification", "explicit_mismatch")}
    for item in (result or {}).get("requirements", []):
        values[item["assessment"]] += 1
    values["total"] = sum(values.values())
    return values


def is_outdated(record: JobFitAnalysis, job: SavedJob | None, profile: CandidateProfile | None) -> bool:
    if job is None or profile is None:
        return True
    _, _, current_job_hash, current_profile_hash = input_state(job, profile)
    return current_job_hash != record.job_hash or current_profile_hash != record.profile_hash


def generate(session: Session, *, owner_id: uuid.UUID, job: SavedJob, key: str, settings: Settings) -> JobFitAnalysis:
    from app.services.privacy_service import require_consent
    require_consent(session, owner_id, "ai_job_fit")
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    if not (job.description or "").strip():
        raise JobFitError(409, "Save a job description before analyzing fit.")
    if profile is None:
        raise JobFitError(409, "Create a candidate profile before analyzing fit.")
    snapshot, facts, job_hash, profile_hash = input_state(job, profile)
    if not facts:
        raise JobFitError(409, "Add at least one usable fact to your candidate profile.")
    payload_hash = _hash({"job_id": str(job.id), "job_hash": job_hash, "profile_hash": profile_hash})
    existing = session.scalar(select(JobFitAnalysis).where(JobFitAnalysis.owner_id == owner_id, JobFitAnalysis.idempotency_key == key))
    if existing:
        if existing.payload_hash != payload_hash:
            raise JobFitError(409, "This idempotency key was already used with different analysis inputs.")
        return existing
    if session.scalar(select(JobFitAnalysis).where(JobFitAnalysis.owner_id == owner_id, JobFitAnalysis.job_id == job.id, JobFitAnalysis.status == "generating")):
        raise JobFitError(409, "A fit analysis is already being generated for this job.")
    request_size = len(snapshot["description"]) + sum(len(fact.value) for fact in facts)
    if request_size > settings.JOBPILOT_AI_MAX_INPUT_CHARS:
        raise JobFitError(413, "The job and profile exceed the AI input limit.")
    try:
        provider = provider_for(settings)
    except SuggestionError as error:
        raise JobFitError(error.status_code, error.message) from error
    from app.services import ai_usage
    try:
        token = ai_usage.reserve(session, owner_id, settings, feature="fit")
    except ai_usage.AIUsageError as error:
        raise JobFitError(error.status_code, error.message) from None
    record = JobFitAnalysis(
        owner_id=owner_id, job_id=job.id, profile_id=profile.id,
        idempotency_key=key, payload_hash=payload_hash, job_hash=job_hash,
        profile_hash=profile_hash, job_snapshot=snapshot,
        profile_facts=[fact.model_dump(mode="json") for fact in facts], status="generating",
        result=None, counts={}, provider=provider.name, model=provider.model,
        prompt_version=JOB_FIT_PROMPT_VERSION,
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise JobFitError(409, "A fit analysis request with this key already exists.") from error
    from app.services.ai_usage import dispatch_guard
    try:
        dispatch_guard(session, owner_id)
        require_consent(session, owner_id, "ai_job_fit")
    except Exception:
        record.status = "failed"
        record.outcome_message = "Dispatch cancelled before provider request; consent or account access changed."
        ai_usage.release(session, owner_id, token)
        session.commit()
        raise
    try:
        output = ai_usage.bounded_call(lambda: provider.analyze(snapshot["description"], facts), settings.JOBPILOT_AI_TIMEOUT_SECONDS)
        result = validate_output(output, snapshot["description"], facts)
        status, message = "ready", None
    except ProviderFailure as error:
        result, status, message = None, "failed", str(error)
    except JobFitError as error:
        result, status, message = None, "failed", error.message
    except Exception:
        result, status, message = None, "failed", "Provider request failed; no automatic retry."
    session.expire_all()
    current = session.get(JobFitAnalysis, record.id)
    if current is None:
        raise JobFitError(404, "Fit analysis no longer exists.")
    current.result = result
    current.counts = counts(result)
    current.status = status
    current.outcome_message = message
    ai_usage.release(session, owner_id, token)
    session.commit()
    session.refresh(current)
    return current


def get_owned(session: Session, *, owner_id: uuid.UUID, analysis_id: uuid.UUID):
    return session.scalar(select(JobFitAnalysis).where(JobFitAnalysis.id == analysis_id, JobFitAnalysis.owner_id == owner_id))


def latest(session: Session, *, owner_id: uuid.UUID, job_id: uuid.UUID):
    return session.scalar(select(JobFitAnalysis).where(JobFitAnalysis.owner_id == owner_id, JobFitAnalysis.job_id == job_id).order_by(JobFitAnalysis.created_at.desc(), JobFitAnalysis.id.desc()).limit(1))


def history(session: Session, *, owner_id: uuid.UUID, job_id: uuid.UUID, page: int, page_size: int):
    filters = (JobFitAnalysis.owner_id == owner_id, JobFitAnalysis.job_id == job_id)
    total = session.scalar(select(func.count()).select_from(JobFitAnalysis).where(*filters)) or 0
    items = list(session.scalars(select(JobFitAnalysis).where(*filters).order_by(JobFitAnalysis.created_at.desc(), JobFitAnalysis.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    return items, total
