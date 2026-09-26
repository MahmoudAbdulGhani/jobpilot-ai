import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.job_application_skills import ApplicationSkillList, ApplicationSkillResponse, SkillConfirmation
from app.services import job_application_skill_service as service

router = APIRouter(prefix="/jobs/{job_id}/application-skills", tags=["application-skills"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=ApplicationSkillList)
def list_skills(job_id: uuid.UUID, db: Database, current_user: CurrentUser):
    try:
        return ApplicationSkillList(items=service.list_current(db, current_user.id, job_id))
    except service.ApplicationSkillError as error:
        raise HTTPException(error.status_code, error.message) from error


@router.post("", response_model=ApplicationSkillResponse)
def confirm(job_id: uuid.UUID, body: SkillConfirmation, db: Database, current_user: CurrentUser):
    try:
        return service.confirm(db, current_user.id, job_id, body.analysis_id, body.requirement_id)
    except service.ApplicationSkillError as error:
        raise HTTPException(error.status_code, error.message) from error


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(job_id: uuid.UUID, skill_id: uuid.UUID, db: Database, current_user: CurrentUser):
    try:
        service.remove(db, current_user.id, job_id, skill_id)
    except service.ApplicationSkillError as error:
        raise HTTPException(error.status_code, error.message) from error
    return Response(status_code=204)
