import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import CandidateProfile, User
from app.schemas.job_fit import JobFitAnalysisList, JobFitAnalysisResponse, JobFitGenerate
from app.services import job_fit_service, job_service

router = APIRouter(prefix="/jobs/{job_id}/fit-analyses", tags=["job-fit"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


def _job(db, user, job_id):
    job = job_service.get_saved_job(db, owner_id=user.id, job_id=job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def _response(db: Session, record, job) -> JobFitAnalysisResponse:
    profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == record.owner_id))
    data = {column.name: getattr(record, column.name) for column in record.__table__.columns}
    data["is_outdated"] = job_fit_service.is_outdated(record, job, profile)
    return JobFitAnalysisResponse.model_validate(data)


@router.post("", response_model=JobFitAnalysisResponse)
def generate(job_id: uuid.UUID, body: JobFitGenerate, db: Database, current_user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]):
    job = _job(db, current_user, job_id)
    try:
        record = job_fit_service.generate(db, owner_id=current_user.id, job=job, key=body.idempotency_key, settings=settings)
    except job_fit_service.JobFitError as error:
        raise HTTPException(error.status_code, error.message) from error
    return _response(db, record, job)


@router.get("/latest", response_model=JobFitAnalysisResponse)
def latest(job_id: uuid.UUID, db: Database, current_user: CurrentUser):
    job = _job(db, current_user, job_id)
    record = job_fit_service.latest(db, owner_id=current_user.id, job_id=job.id)
    if record is None:
        raise HTTPException(404, "Fit analysis not found")
    return _response(db, record, job)


@router.get("", response_model=JobFitAnalysisList)
def history(job_id: uuid.UUID, db: Database, current_user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 10):
    job = _job(db, current_user, job_id)
    items, total = job_fit_service.history(db, owner_id=current_user.id, job_id=job.id, page=page, page_size=page_size)
    return JobFitAnalysisList(items=[_response(db, item, job) for item in items], total=total, page=page, page_size=page_size)


@router.get("/{analysis_id}", response_model=JobFitAnalysisResponse)
def get_analysis(job_id: uuid.UUID, analysis_id: uuid.UUID, db: Database, current_user: CurrentUser):
    job = _job(db, current_user, job_id)
    record = job_fit_service.get_owned(db, owner_id=current_user.id, analysis_id=analysis_id)
    if record is None or record.job_id != job.id:
        raise HTTPException(404, "Fit analysis not found")
    return _response(db, record, job)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(job_id: uuid.UUID, analysis_id: uuid.UUID, db: Database, current_user: CurrentUser):
    job = _job(db, current_user, job_id)
    record = job_fit_service.get_owned(db, owner_id=current_user.id, analysis_id=analysis_id)
    if record is None or record.job_id != job.id:
        raise HTTPException(404, "Fit analysis not found")
    db.delete(record)
    db.commit()
    return Response(status_code=204)
