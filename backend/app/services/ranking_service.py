"""Deterministic cross-job ranking over the owner's own saved data.

No provider calls, no profile/job mutation. Every score component cites a
verbatim job excerpt and the saved profile fact it was compared against.
"""
import hashlib
import re
import uuid
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, SavedJob
from app.models.job_ranking import JobRanking

ENGINE_VERSION = "rank-v1"
MAX_JOBS_PER_RUN = 100

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "has", "from", "that", "this", "who", "can", "all", "any", "per", "etc",
    "including", "include", "role", "team", "work", "working", "join", "help",
    "looking", "seeking", "ideal", "strong", "good", "great", "new", "day",
    "including", "plus", "must", "required", "requirements", "qualifications",
    "responsibilities", "about", "what", "why", "how", "into", "over", "under",
    "know", "able", "candidate", "successful", "opportunity", "using", "use",
}
WORD = re.compile(r"[a-z0-9][a-z0-9+#.-]*")
REQUIREMENT_HINT = re.compile(r"\bmust\b|\brequired?\b|\bneeds?\b|\bessential\b", re.IGNORECASE)
REMOTE_SIGNALS = ("remote", "work from home", "wfh", "distributed", "work-from-home")
ONSITE_SIGNALS = ("on-site", "onsite", "on site", "in-office", "in office", "hybrid")
SENIOR_SIGNALS = ("senior", "staff", "principal", "lead", "architect")
JUNIOR_SIGNALS = ("junior", "entry-level", "entry level", "graduate", "intern", "trainee")


def _tokens(text: str) -> list[str]:
    return [token.strip(".,:;()\"'") for token in WORD.findall((text or "").casefold())]


def _keywords(text: str, minimum: int = 3) -> Counter:
    return Counter(token for token in _tokens(text) if len(token) >= minimum and token not in STOPWORDS)


def _excerpt(text: str, needle: str, limit: int = 200) -> str:
    for line in (text or "").splitlines():
        if needle in line.casefold() and line.strip():
            snippet = line.strip()
            return snippet[:limit]
    snippet = (text or "").strip().replace("\n", " ")
    return snippet[:limit]


def profile_facts(profile: CandidateProfile) -> list[dict]:
    facts: list[dict] = []
    counter = 0

    def add(path: str, value: str):
        nonlocal counter
        value = (value or "").strip()
        if not value:
            return
        counter += 1
        facts.append({"id": f"fact-{counter}", "path": path, "value": value[:2000]})

    add("headline", profile.headline or "")
    add("location", profile.location or "")
    if profile.remote_preference:
        add("remote_preference", profile.remote_preference)
    for skill in profile.skills or []:
        add("skills", skill if isinstance(skill, str) else str(skill))
    for entry in profile.experience or []:
        add("experience", entry if isinstance(entry, str) else " | ".join(
            f"{key}: {val}" for key, val in (entry.items() if isinstance(entry, dict) else []) if val))
    for entry in profile.education or []:
        add("education", entry if isinstance(entry, str) else " | ".join(
            f"{key}: {val}" for key, val in (entry.items() if isinstance(entry, dict) else []) if val))
    for language in profile.languages or []:
        add("languages", language if isinstance(language, str) else str(language))
    return facts


def _canonical_profile(profile: CandidateProfile | None) -> str:
    if profile is None:
        return ""
    parts = [profile.headline or "", profile.location or "", profile.remote_preference or ""]
    for collection in (profile.skills, profile.experience, profile.education, profile.languages):
        for entry in collection or []:
            parts.append(entry if isinstance(entry, str) else str(entry))
    return "\n".join(parts)


def profile_hash(profile: CandidateProfile | None) -> str:
    return hashlib.sha256(_canonical_profile(profile).encode("utf-8")).hexdigest()


def job_hash(job: SavedJob) -> str:
    stamp = job.updated_at.isoformat() if job.updated_at else ""
    return hashlib.sha256(f"{job.id}\n{job.title}\n{job.description or ''}\n{stamp}".encode("utf-8")).hexdigest()


def _fact_with(facts: list[dict], token: str) -> dict | None:
    for fact in facts:
        if token in fact["value"].casefold():
            return fact
    return None


def score_job(job: SavedJob, facts: list[dict], profile_text: str, experience_entries: int) -> dict:
    description = job.description or ""
    reasons: list[dict] = []
    missing: list[str] = []
    risks: list[str] = []
    profile_tokens = set(_tokens(profile_text))
    job_counter = _keywords(description)
    top_terms = [term for term, _ in job_counter.most_common(24)]

    if not description.strip():
        return {"job_id": str(job.id), "title": job.title, "company": job.company, "score": 0,
                "reasons": [], "missing_skills": [],
                "risks": ["No job description saved; ranking needs the job's own text to compare."],
                "recommended_action": "Save the job description first, then re-rank."}

    # 1. Skill/keyword overlap (40).
    matched = [term for term in top_terms if term in profile_tokens]
    skill_points = min(40, len(matched) * 4)
    if matched:
        anchor = _fact_with(facts, matched[0])
        reasons.append({"text": f"Profile covers {len(matched)} of the job's most frequent terms ({', '.join(matched[:5])}).",
                        "evidence": {"job_quote": _excerpt(description, matched[0]),
                                     "profile_fact": (anchor["value"][:200] if anchor else profile_text[:200])}})
    else:
        risks.append("None of the job's most frequent terms appear in the saved profile.")

    # 2. Explicit required-term coverage (20).
    required_terms: list[str] = []
    for line in description.splitlines():
        if REQUIREMENT_HINT.search(line):
            for token in _tokens(line):
                if len(token) >= 4 and token not in STOPWORDS and token not in required_terms:
                    required_terms.append(token)
    required_terms = required_terms[:20]
    if not required_terms:
        required_points = 12
        reasons.append({"text": "The description states no explicit must-have terms, so no required-term penalty applies.",
                        "evidence": {"job_quote": _excerpt(description, top_terms[0] if top_terms else ""),
                                     "profile_fact": (facts[0]["value"][:200] if facts else "")}})
    else:
        covered = [term for term in required_terms if term in profile_tokens]
        absent = [term for term in required_terms if term not in profile_tokens]
        required_points = round(len(covered) / len(required_terms) * 20)
        missing.extend(absent[:8])
        if covered:
            anchor = _fact_with(facts, covered[0])
            reasons.append({"text": f"Profile evidences {len(covered)} of {len(required_terms)} explicit required terms.",
                            "evidence": {"job_quote": _excerpt(description, covered[0]),
                                         "profile_fact": (anchor["value"][:200] if anchor else "")}})
        if absent:
            risks.append(f"Explicit required terms not evidenced in the profile: {', '.join(absent[:5])}.")

    # 3. Location (15).
    job_location = (job.location or "").strip()
    profile_location = ""
    for fact in facts:
        if fact["path"] == "location":
            profile_location = fact["value"]
            break
    lowered = description.casefold()
    remote_job = "remote" in (job_location.casefold()) or any(sig in lowered for sig in ("remote",))
    if job_location and profile_location:
        if job_location.casefold() in profile_location.casefold() or profile_location.casefold() in job_location.casefold() or remote_job:
            location_points = 15
            reasons.append({"text": f"Location is compatible (job: {job_location}; profile: {profile_location}).",
                            "evidence": {"job_quote": job_location, "profile_fact": profile_location[:200]}})
        else:
            location_points = 3
            risks.append(f"Location mismatch: job lists {job_location} while the profile lists {profile_location}.")
    elif remote_job:
        location_points = 12
        reasons.append({"text": "The job is listed as remote, so candidate location is not a blocker.",
                        "evidence": {"job_quote": _excerpt(description, "remote") or job_location,
                                     "profile_fact": profile_location[:200] if profile_location else "No candidate location saved."}})
    else:
        location_points = 8

    # 4. Remote preference (10).
    preference = ""
    for fact in facts:
        if fact["path"] == "remote_preference":
            preference = fact["value"].casefold()
            break
    text_signals_remote = any(sig in lowered for sig in REMOTE_SIGNALS)
    text_signals_onsite = any(sig in lowered for sig in ONSITE_SIGNALS)
    if preference == "remote" and (text_signals_remote or remote_job) and not text_signals_onsite:
        remote_points = 10
        reasons.append({"text": "Remote preference matches a remote-listed job.",
                        "evidence": {"job_quote": _excerpt(description, "remote") or job_location,
                                     "profile_fact": preference}})
    elif preference == "remote" and text_signals_onsite and not text_signals_remote:
        remote_points = 2
        risks.append("Remote preference conflicts with on-site wording in the description.")
    elif preference in {"office", "hybrid"} and text_signals_remote and not text_signals_onsite:
        remote_points = 5
        risks.append(f"{preference.title()} preference against a remote-listed job; confirm eligibility.")
    else:
        remote_points = 6

    # 5. Seniority (15).
    senior_hit = any(sig in lowered for sig in SENIOR_SIGNALS)
    junior_hit = any(sig in lowered for sig in JUNIOR_SIGNALS)
    if senior_hit and not junior_hit:
        if experience_entries >= 3:
            seniority_points = 15
            reasons.append({"text": f"Senior wording fits {experience_entries} saved experience entries.",
                            "evidence": {"job_quote": _excerpt(description, next(s for s in SENIOR_SIGNALS if s in lowered)),
                                         "profile_fact": next((f["value"][:200] for f in facts if f["path"] == "experience"), "")}})
        else:
            seniority_points = 0
            risks.append("Senior wording with fewer than 3 saved experience entries; substantiate senior scope before applying.")
    elif junior_hit and not senior_hit:
        if experience_entries >= 5:
            seniority_points = 8
            risks.append("Entry-level wording against extensive saved experience; confirm the level is acceptable.")
        else:
            seniority_points = 12
    else:
        seniority_points = 8

    score = max(0, min(100, skill_points + required_points + location_points + remote_points + seniority_points))
    for term in top_terms:
        if term not in profile_tokens and term not in missing and len(missing) < 8:
            missing.append(term)
    if score >= 70:
        action = "Strong fit on saved evidence. Consider applying and reuse the evidenced strengths in your pack."
    elif score >= 45:
        action = "Worth reviewing. Close the named gaps or confirm the flagged risks before applying."
    else:
        action = "Low match on saved evidence. Only pursue for a specific reason, and do not add unheld skills."
    return {"job_id": str(job.id), "title": job.title, "company": job.company, "score": score,
            "reasons": reasons, "missing_skills": missing, "risks": risks, "recommended_action": action}


def run_ranking(db: Session, owner_id: uuid.UUID, job_ids: list[uuid.UUID] | None, include_archived: bool) -> JobRanking:
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    facts = profile_facts(profile) if profile else []
    if not facts:
        raise HTTPException(409, "Save candidate profile details before ranking jobs")
    query = select(SavedJob).where(SavedJob.owner_id == owner_id)
    if job_ids is not None:
        query = query.where(SavedJob.id.in_(job_ids))
    if not include_archived:
        query = query.where(SavedJob.is_archived.is_(False))
    jobs = list(db.scalars(query.order_by(SavedJob.created_at.desc(), SavedJob.id.desc()).limit(MAX_JOBS_PER_RUN + 1)))
    if job_ids is not None and len(jobs) != len(set(job_ids)):
        raise HTTPException(404, "Job not found")
    if len(jobs) > MAX_JOBS_PER_RUN:
        raise HTTPException(422, f"Select at most {MAX_JOBS_PER_RUN} jobs per ranking run")
    if not jobs:
        raise HTTPException(409, "Save at least one job before ranking")
    profile_text = _canonical_profile(profile)
    experience_entries = len(profile.experience or []) if profile else 0
    items = [score_job(job, facts, profile_text, experience_entries) for job in jobs]
    items.sort(key=lambda item: (-item["score"], item["title"]))
    run = JobRanking(owner_id=owner_id, profile_hash=profile_hash(profile),
                     job_hashes=[{"job_id": str(job.id), "hash": job_hash(job)} for job in jobs],
                     items=items, engine_version=ENGINE_VERSION)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def current_hashes(db: Session, owner_id: uuid.UUID, run: JobRanking) -> tuple[str, dict[str, str]]:
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    job_ids = [entry["job_id"] for entry in (run.job_hashes or [])]
    jobs = db.scalars(select(SavedJob).where(SavedJob.owner_id == owner_id)) if job_ids else []
    by_id = {str(job.id): job_hash(job) for job in jobs}
    return profile_hash(profile), by_id


def is_stale(db: Session, owner_id: uuid.UUID, run: JobRanking) -> bool:
    current_profile, by_id = current_hashes(db, owner_id, run)
    if current_profile != run.profile_hash:
        return True
    stored = {entry["job_id"]: entry["hash"] for entry in (run.job_hashes or [])}
    for job_id, digest in stored.items():
        if by_id.get(job_id) != digest:
            return True
    return False


def get_run(db: Session, owner_id: uuid.UUID, run_id: uuid.UUID) -> JobRanking:
    run = db.scalar(select(JobRanking).where(JobRanking.id == run_id, JobRanking.owner_id == owner_id))
    if run is None:
        raise HTTPException(404, "Ranking not found")
    return run


def list_runs(db: Session, owner_id: uuid.UUID, page: int, page_size: int) -> dict:
    total = db.scalar(select(func.count()).select_from(JobRanking).where(
        JobRanking.owner_id == owner_id)) or 0
    rows = list(db.scalars(select(JobRanking).where(JobRanking.owner_id == owner_id).order_by(
        JobRanking.created_at.desc(), JobRanking.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": list(rows), "total": total, "page": page, "page_size": page_size}


def delete_run(db: Session, owner_id: uuid.UUID, run_id: uuid.UUID) -> None:
    run = get_run(db, owner_id, run_id)
    db.delete(run)
    db.commit()
