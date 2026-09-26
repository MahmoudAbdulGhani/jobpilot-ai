"""Owner-scoped, job-specific self-attested skills from verified fit gaps."""
import uuid
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CandidateProfile, JobApplicationSkill, SavedJob
from app.services import job_fit_service


class ApplicationSkillError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code, self.message = status_code, message
        super().__init__(message)


def _current(session: Session, owner_id: uuid.UUID, job_id: uuid.UUID):
    job = session.scalar(select(SavedJob).where(SavedJob.id == job_id, SavedJob.owner_id == owner_id))
    if job is None:
        raise ApplicationSkillError(404, "Job not found")
    analysis = job_fit_service.latest(session, owner_id=owner_id, job_id=job_id)
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
    if analysis is None or analysis.status != "ready" or job_fit_service.is_outdated(analysis, job, profile):
        return job, None
    return job, analysis


def list_current(session: Session, owner_id: uuid.UUID, job_id: uuid.UUID):
    _, analysis = _current(session, owner_id, job_id)
    if analysis is None:
        return []
    return list(session.scalars(select(JobApplicationSkill).where(
        JobApplicationSkill.owner_id == owner_id,
        JobApplicationSkill.job_id == job_id,
        JobApplicationSkill.analysis_id == analysis.id,
    ).order_by(JobApplicationSkill.created_at, JobApplicationSkill.id)))


def confirm(session: Session, owner_id: uuid.UUID, job_id: uuid.UUID, analysis_id: uuid.UUID, requirement_id: str):
    _, analysis = _current(session, owner_id, job_id)
    if analysis is None or analysis.id != analysis_id:
        raise ApplicationSkillError(409, "Run a current job-fit analysis before confirming a skill.")
    from app.schemas.job_fit import JobFitResultResponse
    result = JobFitResultResponse.model_validate(analysis.result)
    item = next((entry for entry in result.missing_skills if entry["requirement_id"] == requirement_id), None)
    if item is None:
        raise ApplicationSkillError(422, "This requirement is not a verified missing skill.")
    skill = item["skill"].strip()
    if re.search(r"\b(citizenship|citizen|clearance|certification|certified|degree|years? of experience|work authorization|visa)\b", skill, re.I):
        raise ApplicationSkillError(422, "Eligibility and credentials cannot be confirmed as application skills.")
    key = skill.casefold()
    existing = session.scalar(select(JobApplicationSkill).where(
        JobApplicationSkill.owner_id == owner_id, JobApplicationSkill.job_id == job_id,
        JobApplicationSkill.analysis_id == analysis.id, JobApplicationSkill.skill_key == key))
    if existing:
        return existing
    record = JobApplicationSkill(owner_id=owner_id, job_id=job_id, analysis_id=analysis.id,
                                 skill_key=key, skill=skill, importance=item["importance"],
                                 job_quote=item["job_quote"])
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(JobApplicationSkill).where(
            JobApplicationSkill.owner_id == owner_id, JobApplicationSkill.job_id == job_id,
            JobApplicationSkill.analysis_id == analysis_id, JobApplicationSkill.skill_key == key))
        if existing:
            return existing
        raise
    session.refresh(record)
    return record


def remove(session: Session, owner_id: uuid.UUID, job_id: uuid.UUID, skill_id: uuid.UUID):
    record = session.scalar(select(JobApplicationSkill).where(
        JobApplicationSkill.id == skill_id, JobApplicationSkill.owner_id == owner_id,
        JobApplicationSkill.job_id == job_id))
    if record is None:
        raise ApplicationSkillError(404, "Confirmed skill not found")
    session.delete(record)
    session.commit()
