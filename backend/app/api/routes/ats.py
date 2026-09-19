"""ATS/readiness reports: deterministic checks over approved packs. Read-only inputs."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import CandidateProfile, SavedJob, User
from app.schemas.ats import (AtsImproveRequest, AtsImproveResponse, AtsReportList,
                             AtsReportRequest, AtsReportResponse)
from app.services import application_pack_service, ats_service
from app.services.application_pack_service import PackError

router = APIRouter(prefix="/jobs/{job_id}/packs/{pack_id}/ats-reports", tags=["ats-readiness"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=AtsReportResponse, status_code=201)
def create_report(job_id: uuid.UUID, pack_id: uuid.UUID, body: AtsReportRequest,
                  db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return ats_service.generate(db, owner_id=current_user.id, job_id=job_id,
                                pack_id=pack_id, pack_version=body.pack_version)


@router.post("/{report_id}/improve", response_model=AtsImproveResponse, status_code=201)
def improve_report(job_id: uuid.UUID, pack_id: uuid.UUID, report_id: uuid.UUID,
                   body: AtsImproveRequest, db: Database, current_user: CurrentUser,
                   response: Response, settings: Annotated[Settings, Depends(get_settings)]):
    response.headers["Cache-Control"] = "no-store"
    report = ats_service.get_report(db, owner_id=current_user.id, job_id=job_id,
                                    pack_id=pack_id, report_id=report_id)
    try:
        pack, version, notes = application_pack_service.improve_pack(
            db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id,
            report_id=report_id, target_version=report.pack_version,
            checks=report.checks, readiness_score=report.readiness_score,
            body=body, settings=settings)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error
    description = db.scalar(select(SavedJob.description).where(
        SavedJob.id == job_id, SavedJob.owner_id == current_user.id)) or ""
    profile = db.scalar(select(CandidateProfile).where(
        CandidateProfile.owner_id == current_user.id))
    preview = ats_service.build_checks(description or "", version.cv, version.cover_letter, profile)
    return AtsImproveResponse(
        report_id=report_id, job_id=job_id, pack_id=pack.id,
        approved_version=report.pack_version, version_number=version.number,
        review_notes=notes, preview_checks=preview,
        preview_readiness=ats_service.readiness(preview))


@router.get("/latest", response_model=AtsReportResponse | None)
def latest_report(job_id: uuid.UUID, pack_id: uuid.UUID, db: Database,
                  current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return ats_service.latest(db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id)


@router.get("", response_model=AtsReportList)
def list_reports(job_id: uuid.UUID, pack_id: uuid.UUID, db: Database, current_user: CurrentUser,
                 response: Response, page: Annotated[int, Query(ge=1)] = 1,
                 page_size: Annotated[int, Query(ge=1, le=50)] = 10):
    response.headers["Cache-Control"] = "no-store"
    return ats_service.history(db, owner_id=current_user.id, job_id=job_id,
                               pack_id=pack_id, page=page, page_size=page_size)


@router.get("/{report_id}", response_model=AtsReportResponse)
def get_report(job_id: uuid.UUID, pack_id: uuid.UUID, report_id: uuid.UUID,
               db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return ats_service.get_report(db, owner_id=current_user.id, job_id=job_id,
                                  pack_id=pack_id, report_id=report_id)


@router.delete("/{report_id}", status_code=204)
def delete_report(job_id: uuid.UUID, pack_id: uuid.UUID, report_id: uuid.UUID,
                  db: Database, current_user: CurrentUser):
    ats_service.delete_report(db, owner_id=current_user.id, job_id=job_id,
                              pack_id=pack_id, report_id=report_id)
    return Response(status_code=204)
