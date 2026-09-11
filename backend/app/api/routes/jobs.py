import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.jobs import (
    MAX_PAGE_SIZE,
    SEARCH_MAX_LENGTH,
    SavedJobCreate,
    SavedJobListResponse,
    SavedJobResponse,
    SavedJobUpdate,
)
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


def _owned_job_or_404(db: Session, user: User, job_id: uuid.UUID):
    job = job_service.get_saved_job(db, owner_id=user.id, job_id=job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("", response_model=SavedJobResponse, status_code=status.HTTP_201_CREATED)
def create_job(body: SavedJobCreate, db: Database, current_user: CurrentUser):
    return job_service.create_saved_job(db, owner_id=current_user.id, data=body)


@router.get("", response_model=SavedJobListResponse)
def list_jobs(
    db: Database,
    current_user: CurrentUser,
    archived: bool = False,
    search: Annotated[str | None, Query(max_length=SEARCH_MAX_LENGTH)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
):
    jobs, total = job_service.list_saved_jobs(
        db,
        owner_id=current_user.id,
        archived=archived,
        search=search,
        page=page,
        page_size=page_size,
    )
    return SavedJobListResponse(
        items=jobs, total=total, page=page, page_size=page_size
    )


@router.get("/{job_id}", response_model=SavedJobResponse)
def get_job(job_id: uuid.UUID, db: Database, current_user: CurrentUser):
    return _owned_job_or_404(db, current_user, job_id)


@router.patch("/{job_id}", response_model=SavedJobResponse)
def update_job(
    job_id: uuid.UUID,
    body: SavedJobUpdate,
    db: Database,
    current_user: CurrentUser,
):
    job = _owned_job_or_404(db, current_user, job_id)
    return job_service.update_saved_job(db, job=job, data=body)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> Response:
    job = _owned_job_or_404(db, current_user, job_id)
    job_service.delete_saved_job(db, job=job)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
