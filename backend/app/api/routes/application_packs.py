import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.application_packs import (
    PackGenerate,
    PackList,
    PackOptions,
    PackOperations,
    PackResponse,
    PackSave,
    PackVersionList,
)
from app.services import application_pack_service, pack_export
from app.services.application_pack_service import PackError

router = APIRouter(
    prefix="/jobs/{job_id}/application-packs", tags=["application-packs"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get("/options", response_model=PackOptions)
def options(job_id: uuid.UUID, db: Database, current_user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]):
    try:
        return application_pack_service.options(db, owner_id=current_user.id, job_id=job_id, settings=settings)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.post("", response_model=PackResponse)
def generate(job_id: uuid.UUID, body: PackGenerate, db: Database, current_user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]):
    try:
        pack = application_pack_service.generate(
            db, owner_id=current_user.id, job_id=job_id, body=body, settings=settings)
        return application_pack_service.response(db, pack)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.get("", response_model=PackList)
def list_packs(job_id: uuid.UUID, db: Database, current_user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 5):
    try:
        return application_pack_service.list_packs(db, owner_id=current_user.id, job_id=job_id, page=page, page_size=page_size)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.get("/{pack_id}", response_model=PackResponse)
def get_pack(job_id: uuid.UUID, pack_id: uuid.UUID, db: Database, current_user: CurrentUser):
    try:
        return application_pack_service.response(db, application_pack_service.get_owned(db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id))
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.patch("/{pack_id}/draft", response_model=PackResponse)
def save_draft(job_id: uuid.UUID, pack_id: uuid.UUID, body: PackSave, db: Database, current_user: CurrentUser):
    try:
        pack, version = application_pack_service.edit_or_approve(
            db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id, body=body, approve=False)
        return application_pack_service.response(db, pack, version)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.post("/{pack_id}/approve", response_model=PackResponse)
def approve(job_id: uuid.UUID, pack_id: uuid.UUID, body: PackOperations, db: Database, current_user: CurrentUser):
    try:
        pack, version = application_pack_service.edit_or_approve(
            db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id, body=body, approve=True)
        return application_pack_service.response(db, pack, version)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.get("/{pack_id}/versions", response_model=PackVersionList)
def list_versions(job_id: uuid.UUID, pack_id: uuid.UUID, db: Database, current_user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=50)] = 5):
    try:
        return application_pack_service.list_versions(db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id, page=page, page_size=page_size)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error


@router.get("/{pack_id}/versions/{version_number}/download")
def download(job_id: uuid.UUID, pack_id: uuid.UUID, version_number: int, db: Database, current_user: CurrentUser, document: Literal["cv", "cover_letter"] = "cv", format: Literal["pdf", "docx"] = "pdf"):
    try:
        pack, version = application_pack_service.get_download_version(
            db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id, version_number=version_number)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error
    try:
        payload = version.cv if document == "cv" else version.cover_letter
        body = {"blocks": [{"kind": block["kind"], "text": block["text"]}
                           for block in payload["blocks"]]}
        raw = pack_export.render_document(body, format)
    except pack_export.ExportFailure as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=error.message) from error
    name = f"{document}-{version_number}.{format}"
    return Response(content=raw, media_type={"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[format], headers={"Content-Disposition": f"attachment; filename={name}"})


@router.delete("/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pack(job_id: uuid.UUID, pack_id: uuid.UUID, db: Database, current_user: CurrentUser):
    try:
        application_pack_service.delete_pack(
            db, owner_id=current_user.id, job_id=job_id, pack_id=pack_id)
    except PackError as error:
        raise HTTPException(error.status_code, detail=error.message) from error
    return Response(status_code=204)
