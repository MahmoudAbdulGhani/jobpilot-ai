import uuid
from datetime import datetime, timezone
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
from urllib.parse import quote
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import ResumeExtraction, User
from app.schemas.resumes import (
    ResumeExtractionResponse,
    ResumeExtractionUpdate,
    ResumeListResponse,
    ResumeResponse,
    ResumeUpdate,
)
from app.services import resume_extraction, resume_service, resume_store, resume_validation

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
        content_type=resume_validation.media_type(extension),
    )


@router.get("", response_model=ResumeListResponse)
def list_resumes(db: Database, current_user: CurrentUser) -> ResumeListResponse:
    items = resume_service.list_resumes(db, owner_id=current_user.id)
    return ResumeListResponse(items=items)


@router.get("/{resume_id}/download")
def download_resume(
    resume_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> Response:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    data = resume_store.read_bytes(resume.id)
    if data is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=GENERIC_NOT_FOUND_DETAIL
        )
    return Response(
        content=data,
        media_type=resume_validation.media_type(resume.file_extension),
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(resume.original_filename, safe=''),
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{resume_id}/extraction", response_model=ResumeExtractionResponse)
def get_resume_extraction(
    resume_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> ResumeExtractionResponse:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    extraction = resume_service.get_extraction(db, resume_id=resume.id)
    if extraction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Extraction not found")
    return extraction


@router.post("/{resume_id}/extract", response_model=ResumeExtractionResponse)
def extract_resume_text(
    resume_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> ResumeExtractionResponse:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    resume_service.lock_resume(db, resume_id=resume.id)
    extraction = resume_service.get_extraction(db, resume_id=resume.id)
    if extraction is not None and extraction.status == "succeeded":
        return extraction
    if extraction is not None and extraction.status == "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Extraction is already in progress"
        )
    if extraction is None:
        extraction = ResumeExtraction(resume_id=resume.id, status="pending")
        db.add(extraction)
    else:
        extraction.status = "pending"
        extraction.failure_code = None
        extraction.failure_message = None
    db.commit()
    db.refresh(extraction)

    try:
        data = resume_store.read_bytes(resume.id)
    except resume_store.StorageUnavailable:
        extraction.status = "failed"
        extraction.failure_code = "storage_unavailable"
        extraction.failure_message = "Private document storage is unavailable."
        db.commit()
        raise
    if data is None:
        extraction.status = "failed"
        extraction.failure_code = "missing_source"
        extraction.failure_message = "The stored resume file is unavailable."
    else:
        settings = get_settings()
        extraction.parser_name, extraction.parser_version = (
            resume_extraction.parser_identity(resume.file_extension)
        )
        try:
            text, parser_name, parser_version = resume_extraction.extract(
                data,
                resume.file_extension,
                timeout_seconds=settings.RESUME_EXTRACTION_TIMEOUT_SECONDS,
                max_chars=settings.RESUME_EXTRACTION_MAX_CHARS,
                max_pages=settings.RESUME_EXTRACTION_MAX_PAGES,
                max_blocks=settings.RESUME_EXTRACTION_MAX_BLOCKS,
            )
            extraction.status = "succeeded"
            extraction.original_text = text
            extraction.draft_text = text
            extraction.parser_name = parser_name
            extraction.parser_version = parser_version
            extraction.failure_code = None
            extraction.failure_message = None
            extraction.reviewed_at = None
        except resume_extraction.ExtractionFailure as error:
            extraction.status = "failed"
            extraction.failure_code = error.code
            extraction.failure_message = error.message
        except Exception:
            extraction.status = "failed"
            extraction.failure_code = "processing_error"
            extraction.failure_message = "The document could not be extracted safely."
    db.commit()
    db.refresh(extraction)
    return extraction


@router.patch("/{resume_id}/extraction", response_model=ResumeExtractionResponse)
def update_resume_extraction(
    resume_id: uuid.UUID,
    body: ResumeExtractionUpdate,
    db: Database,
    current_user: CurrentUser,
) -> ResumeExtractionResponse:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    extraction = resume_service.get_extraction(db, resume_id=resume.id)
    if extraction is None or extraction.status != "succeeded":
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="No extracted text is ready to edit"
        )
    if len(body.draft_text) > get_settings().RESUME_EXTRACTION_MAX_CHARS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Edited text is too large"
        )
    if body.draft_text != extraction.draft_text:
        extraction.draft_text = body.draft_text
        extraction.reviewed_at = None
    db.commit()
    db.refresh(extraction)
    return extraction


@router.post("/{resume_id}/extraction/confirm", response_model=ResumeExtractionResponse)
def confirm_resume_extraction(
    resume_id: uuid.UUID, db: Database, current_user: CurrentUser
) -> ResumeExtractionResponse:
    resume = _owned_resume_or_404(db, current_user, resume_id)
    extraction = resume_service.get_extraction(db, resume_id=resume.id)
    if (
        extraction is None
        or extraction.status != "succeeded"
        or not extraction.draft_text
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="No extracted text is ready to confirm"
        )
    if extraction.reviewed_at is None:
        extraction.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(extraction)
    return extraction


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
