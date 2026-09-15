import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.application_tracking import ApplicationCreate, ApplicationListResponse, ApplicationResponse, ApplicationStatusEventResponse, ApplicationUpdate
from app.services import application_tracking_service
from app.services.application_pack_service import PackError

router = APIRouter(
    prefix="/jobs/{job_id}/applications", tags=["application-tracking"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def create_application(job_id: uuid.UUID, body: ApplicationCreate, db: Database, current_user: CurrentUser):
    try:
        body.job_id = job_id
        app = application_tracking_service.create_application(
            db, owner_id=current_user.id, payload=body)
        return app
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.get("", response_model=ApplicationListResponse)
def list_applications(job_id: uuid.UUID, db: Database, current_user: CurrentUser,
                      page: Annotated[int, Query(ge=1)] = 1,
                      page_size: Annotated[int, Query(ge=1, le=50)] = 10,
                      status_filter: Annotated[str | None, Query(alias="status")] = None):
    try:
        return application_tracking_service.list_applications(db, owner_id=current_user.id, page=page, page_size=page_size, status=status_filter, job_id=job_id)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(job_id: uuid.UUID, application_id: uuid.UUID, db: Database, current_user: CurrentUser):
    try:
        return application_tracking_service.get_record(db, owner_id=current_user.id, job_id=job_id, app_id=application_id)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.patch("/{application_id}", response_model=ApplicationResponse)
def update_application(job_id: uuid.UUID, application_id: uuid.UUID, body: ApplicationUpdate, db: Database, current_user: CurrentUser):
    try:
        return application_tracking_service.update_application(db, owner_id=current_user.id, job_id=job_id, app_id=application_id, payload=body)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(job_id: uuid.UUID, application_id: uuid.UUID, db: Database, current_user: CurrentUser):
    try:
        application_tracking_service.delete_application(
            db, owner_id=current_user.id, job_id=job_id, app_id=application_id)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error
    return Response(status_code=204)


@router.get("/{application_id}/events", response_model=dict)
def list_events(job_id: uuid.UUID, application_id: uuid.UUID, db: Database, current_user: CurrentUser,
                page: Annotated[int, Query(ge=1)] = 1,
                page_size: Annotated[int, Query(ge=1, le=50)] = 10):
    try:
        events = application_tracking_service.list_events(
            db, owner_id=current_user.id, job_id=job_id, app_id=application_id)
        return {"items": [ApplicationStatusEventResponse.model_validate(e) for e in events], "total": len(events), "page": page, "page_size": page_size}
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


router_global = APIRouter(prefix="/applications",
                          tags=["application-tracking"])


@router_global.get("", response_model=ApplicationListResponse)
def list_all_applications(db: Database, current_user: CurrentUser,
                          page: Annotated[int, Query(ge=1)] = 1,
                          page_size: Annotated[int, Query(ge=1, le=50)] = 10,
                          status_filter: Annotated[str | None, Query(
                              alias="status")] = None,
                          job_id: Annotated[uuid.UUID | None, Query()] = None):
    try:
        return application_tracking_service.list_applications(db, owner_id=current_user.id, page=page, page_size=page_size, status=status_filter, job_id=job_id)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error
