"""Deterministic ATS/readiness checks over an approved application pack.

Every check inspects explicit content only: the approved CV/cover-letter
blocks, the saved job description and the saved profile. Nothing is inferred,
no provider is called, and existing pack/job validation is untouched.
"""
import hashlib
import json
import re
import uuid
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApplicationPack, ApplicationPackVersion, CandidateProfile, SavedJob
from app.models.ats_report import AtsReport

REPORT_VERSION = "ats-v1"
GENERIC_HEADINGS = {"summary", "contact", "experience", "education", "skills",
                    "projects", "languages", "cover letter", "curriculum vitae",
                    "additional information"}

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")
DATE_RANGE = re.compile(r"(19|20)\d{2}\s*[–—-]\s*((19|20)\d{2}|present|current|now)", re.IGNORECASE)
WORD = re.compile(r"[a-z0-9][a-z0-9+#.-]*")
REQUIREMENT_HINT = re.compile(r"\bmust\b|\brequired?\b|\bneeds?\b|\bessential\b", re.IGNORECASE)
STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "has", "from", "that", "this", "who", "can", "all", "any", "per", "etc",
    "including", "include", "role", "team", "work", "working", "join", "help",
    "looking", "seeking", "ideal", "strong", "good", "great", "new", "day",
    "plus", "must", "required", "requirements", "qualifications",
    "responsibilities", "about", "what", "why", "how", "into", "over",
    "under", "know", "able", "candidate", "successful", "opportunity",
    "using", "use", "years", "year", "experience", "experienced",
}


def _tokens(text: str) -> list[str]:
    return [token.strip(".,:;()\"'") for token in WORD.findall((text or "").casefold())]


def _doc_text(document: dict) -> str:
    return "\n".join(str(block.get("text", "")) for block in (document or {}).get("blocks", []))


def _blocks(document: dict) -> list[dict]:
    blocks = (document or {}).get("blocks", [])
    return [block for block in blocks if isinstance(block, dict)]


def _keyword_coverage(job_description: str, cv_text: str) -> dict:
    counter = Counter(token for token in _tokens(job_description)
                      if len(token) >= 4 and token not in STOPWORDS)
    top = [term for term, _ in counter.most_common(20)]
    cv_tokens = set(_tokens(cv_text))
    covered = [term for term in top if term in cv_tokens]
    missing = [term for term in top if term not in cv_tokens]
    ratio = len(covered) / len(top) if top else 1.0
    status = "pass" if ratio >= 0.7 else ("warn" if ratio >= 0.4 else "fail")
    return {"id": "keyword_coverage", "label": "Keyword coverage",
            "status": status,
            "detail": (f"{len(covered)} of {len(top)} frequent job terms appear in the CV. "
                       if top else "The job description has no frequent terms to compare."),
            "evidence": [f"Covered: {', '.join(covered[:10]) or 'none'}",
                         f"Missing: {', '.join(missing[:10]) or 'none'}"]}


def _contact_fields(cv_text: str) -> dict:
    email = bool(EMAIL_PATTERN.search(cv_text or ""))
    phone = bool(PHONE_PATTERN.search(cv_text or ""))
    status = "pass" if email and phone else ("warn" if email or phone else "fail")
    return {"id": "contact_fields", "label": "Contact fields",
            "status": status,
            "detail": f"Email {'present' if email else 'missing'}; phone {'present' if phone else 'missing'}.",
            "evidence": [f"email:{'found' if email else 'not found'}",
                         f"phone:{'found' if phone else 'not found'}"]}


def _date_consistency(cv_text: str) -> dict:
    problems: list[str] = []
    for match in DATE_RANGE.finditer(cv_text or ""):
        start = int(match.group(0)[:4])
        end_raw = match.group(2).lower()
        if end_raw.isdigit() and int(end_raw) < start:
            problems.append(match.group(0).strip()[:60])
    status = "fail" if problems else "pass"
    return {"id": "date_consistency", "label": "Date consistency",
            "status": status,
            "detail": ("Date ranges ending before they start: " + "; ".join(problems)
                       if problems else "No date range ends before it starts."),
            "evidence": problems[:5] or ["No contradictory year ranges found in the CV text."]}


def _duplicate_skills(profile: CandidateProfile | None) -> dict:
    skills = [str(skill) for skill in (profile.skills if profile else []) or []]
    seen: set[str] = set()
    duplicates: list[str] = []
    for skill in skills:
        folded = skill.casefold().strip()
        if folded in seen and folded not in duplicates:
            duplicates.append(skill)
        seen.add(folded)
    status = "warn" if duplicates else "pass"
    return {"id": "duplicate_skills", "label": "Duplicate skills",
            "status": status,
            "detail": ("Repeated skills: " + ", ".join(duplicates)
                       if duplicates else "No case-insensitive duplicate skills in the saved profile."),
            "evidence": duplicates[:5] or ["Skill list has no repeats."]}


def _unsupported_claims(cv_blocks: list[dict], letter_blocks: list[dict]) -> dict:
    offenders: list[str] = []
    for block in cv_blocks + letter_blocks:
        kind = str(block.get("kind", "")).casefold()
        text = str(block.get("text", "")).strip()
        evidence = block.get("evidence") or []
        if kind != "heading" and text and not evidence and text.casefold() not in GENERIC_HEADINGS:
            offenders.append(f"{block.get('id', 'block')}: {text[:80]}")
    status = "fail" if offenders else "pass"
    return {"id": "unsupported_claims", "label": "Unsupported claims",
            "status": status,
            "detail": (f"{len(offenders)} factual blocks lack evidence references."
                       if offenders else "Every factual block carries an evidence reference."),
            "evidence": offenders[:5] or ["All factual blocks reference evidence."]}


def _evidence_gaps(job_description: str, pack_text: str) -> dict:
    required: list[str] = []
    for line in (job_description or "").splitlines():
        if REQUIREMENT_HINT.search(line):
            for token in _tokens(line):
                if len(token) >= 4 and token not in STOPWORDS and token not in required:
                    required.append(token)
    pack_tokens = set(_tokens(pack_text))
    gaps = [term for term in required[:20] if term not in pack_tokens]
    status = "warn" if gaps else "pass"
    return {"id": "evidence_gaps", "label": "Evidence gaps",
            "status": status,
            "detail": ("Explicit job requirements with no supporting pack text: " + ", ".join(gaps[:8])
                       if gaps else "Every explicit job requirement is addressed in the pack text."),
            "evidence": gaps[:8] or ["No unaddressed explicit requirements."]}


def inputs_hash(pack_id: uuid.UUID, number: int, cv: dict, letter: dict, job_description: str) -> str:
    payload = json.dumps({"pack_id": str(pack_id), "number": number, "cv": cv,
                          "letter": letter, "job": job_description or ""}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_checks(job_description: str, cv: dict, letter: dict, profile: CandidateProfile | None) -> list[dict]:
    cv_text = _doc_text(cv)
    pack_text = f"{cv_text}\n{_doc_text(letter)}"
    cv_blocks = _blocks(cv)
    letter_blocks = _blocks(letter)
    return [_keyword_coverage(job_description, cv_text),
            _contact_fields(cv_text),
            _date_consistency(cv_text),
            _duplicate_skills(profile),
            _unsupported_claims(cv_blocks, letter_blocks),
            _evidence_gaps(job_description, pack_text)]


def readiness(checks: list[dict]) -> int:
    if not checks:
        return 0
    weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    return round(100 * sum(weights.get(check["status"], 0.0) for check in checks) / len(checks))


def _owned_pack(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID):
    job = db.scalar(select(SavedJob).where(SavedJob.id == job_id, SavedJob.owner_id == owner_id))
    if job is None:
        raise HTTPException(404, "Job not found")
    pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == pack_id,
                                                  ApplicationPack.owner_id == owner_id,
                                                  ApplicationPack.job_id == job_id))
    if pack is None:
        raise HTTPException(404, "Application pack not found")
    return job, pack


def generate(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID,
             pack_version: int | None) -> AtsReport:
    job, pack = _owned_pack(db, owner_id, job_id, pack_id)
    query = select(ApplicationPackVersion).where(ApplicationPackVersion.pack_id == pack_id)
    if pack_version is not None:
        query = query.where(ApplicationPackVersion.number == pack_version)
    else:
        query = query.where(ApplicationPackVersion.number == pack.current_version)
    version = db.scalar(query)
    if version is None:
        raise HTTPException(404, "Pack version not found")
    if version.approved_at is None:
        raise HTTPException(409, "Approve the pack version before checking readiness")
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    checks = build_checks(job.description or "", version.cv, version.cover_letter, profile)
    report = AtsReport(owner_id=owner_id, job_id=job_id, pack_id=pack_id,
                       pack_version=version.number, checks=checks,
                       readiness_score=readiness(checks), report_version=REPORT_VERSION,
                       inputs_hash=inputs_hash(pack_id, version.number, version.cv,
                                               version.cover_letter, job.description or ""))
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def get_report(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID, report_id: uuid.UUID):
    _owned_pack(db, owner_id, job_id, pack_id)
    report = db.scalar(select(AtsReport).where(AtsReport.id == report_id, AtsReport.owner_id == owner_id,
                                              AtsReport.job_id == job_id, AtsReport.pack_id == pack_id))
    if report is None:
        raise HTTPException(404, "Readiness report not found")
    return report


def latest(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID):
    _owned_pack(db, owner_id, job_id, pack_id)
    return db.scalar(select(AtsReport).where(AtsReport.owner_id == owner_id, AtsReport.job_id == job_id,
                                            AtsReport.pack_id == pack_id).order_by(
        AtsReport.created_at.desc(), AtsReport.id.desc()))


def history(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID, page: int, page_size: int):
    _owned_pack(db, owner_id, job_id, pack_id)
    total = db.scalar(select(func.count()).select_from(AtsReport).where(
        AtsReport.owner_id == owner_id, AtsReport.job_id == job_id, AtsReport.pack_id == pack_id)) or 0
    rows = list(db.scalars(select(AtsReport).where(
        AtsReport.owner_id == owner_id, AtsReport.job_id == job_id, AtsReport.pack_id == pack_id).order_by(
        AtsReport.created_at.desc(), AtsReport.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def delete_report(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID, report_id: uuid.UUID):
    report = get_report(db, owner_id, job_id, pack_id, report_id)
    db.delete(report)
    db.commit()
