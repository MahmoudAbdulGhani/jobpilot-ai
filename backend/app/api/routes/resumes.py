import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.resumes import ResumeListResponse, ResumeResponse, ResumeUpdate
from app.services import resume_service, resume_store, resume_validation

router = APIRouter(prefix="/resumes", tags=["resumes"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]

_READ_CHUNK_SIZE = 64 * 1024
GENERIC_NOT_FOUND_DETAIL = "Resume not found"


def _owned_resume_or_404(db: Session, user: User, resume_id: uuid.UUID):
    resume = resume_service.get_resume(
        db, owner_id=user.id, resume_id=resume_id
    )
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=GENERIC_NOT_FOUND_DETAIL)
    return resume


@router.post(
    "", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED
)
async def upload_resume(
    file: Annotated[UploadFile, File(...)],
    db: Database,
    current_user: CurrentUser,
) -> ResumeResponse:
    filename = resume_validation.sanitize_filename(file.filename)
    if filename is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Choose a file to upload."
        )
    if len(filename) > resume_validation.MAX_FILENAME_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The file name is too long "
                f"({resume_validation.MAX_FILENAME_LENGTH} character limit)."
            ),
        )
    extension = resume_validation.extension_of(filename)
    if not resume_validation.is_allowed_extension(extension):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Upload a PDF or DOCX resume.",
        )

    limit = get_settings().RESUME_MAX_SIZE_MB * 1024 * 1024
    chunks = []
    total = 0
    while total <= limit:
        chunk = await file.read(min(_READ_CHUNK_SIZE, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    else:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "File too large. Resumes are limited to "
                f"{get_settings().RESUME_MAX_SIZE_MB} MiB."
            ),
        )
    await file.close()

    data = b"".join(chunks)
    if not data:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The file is empty."
        )

    if extension == "pdf":
        if not resume_validation.is_valid_pdf(data):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This is not a valid PDF file.",
            )
    else:
        if not resume_validation.is_valid_docx(data):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This is not a valid DOCX file.",
            )

    return resume_service.create_resume(
        db,
        owner_id=current_user.id,
        original_filename=filename,
        display_name=filename,
        file_extension=extension,
        size_bytes=total,
        data=data,
    )


@router.get("", response_model=ResumeListResponse)
def list_resumes(db: Database, current_user: CurrentUser) -> ResumeListResponse:
    items = resume_service.list_resumes(db, owner_id=current_user.id)
    return ResumeListResponse(items=items)


@router.get("/{resume_id}/download")
def download_resume(
    resume_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> FileResponse:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    path = resume_store.file_path(resume.id)
    if not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=GENERIC_NOT_FOUND_DETAIL
        )
    return FileResponse(
        path=path,
        media_type=resume_validation.media_type(resume.file_extension),
        filename=resume.original_filename,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{resume_id}", response_model=ResumeResponse)
def update_resume(
    resume_id: uuid.UUID,
    body: ResumeUpdate,
    db: Database,
    current_user: CurrentUser,
) -> ResumeResponse:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    return resume_service.update_resume(
        db, resume=resume, owner_id=current_user.id, data=body
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> Response:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    resume_service.delete_resume(db, resume=resume)
    return Response(status_code=status.HTTP_204_NO_CONTENT)