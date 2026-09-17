import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from app.api.routes.jobs import CurrentUser, Database
from app.core.config import get_settings
from app.models import EmailApplication, ApplicationPack, ApplicationPackVersion, SavedJob
from app.schemas.email_applications import EmailApproval, EmailReview
from app.services import email_application_service as service
from app.services.application_pack_service import PackError
from app.services.mailbox_provider import MailboxError
from app.services.pack_export import ExportFailure

router = APIRouter(prefix="/jobs/{job_id}/email-applications", tags=["email applications"])


def handle(operation):
    try:
        return operation()
    except PackError as error:
        raise HTTPException(error.status_code, error.message) from None
    except MailboxError as error:
        raise HTTPException(error.status, error.code) from None
    except ExportFailure as error:
        raise HTTPException(422, error.message) from None


@router.get("")
def listing(job_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not db.scalar(select(SavedJob.id).where(SavedJob.id == job_id, SavedJob.owner_id == current_user.id)):
        raise HTTPException(404, "Job not found")
    versions = db.execute(select(ApplicationPackVersion).join(ApplicationPack).where(
        ApplicationPack.owner_id == current_user.id, ApplicationPack.job_id == job_id,
        ApplicationPack.status == "ready", ApplicationPackVersion.approved_at.is_not(None))
        .order_by(ApplicationPackVersion.created_at.desc()).limit(100)).scalars()
    attempts = db.scalars(select(EmailApplication).where(EmailApplication.owner_id == current_user.id,
        EmailApplication.job_id == job_id).order_by(EmailApplication.created_at.desc()).limit(20))
    return {"versions": [{"pack_id": str(v.pack_id), "number": v.number, "approved_at": v.approved_at} for v in versions],
        "items": [service.public(a) for a in attempts]}


@router.post("")
def review(job_id: uuid.UUID, body: EmailReview, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(service.create_review(db, current_user.id, job_id, body, settings)))


@router.get("/{attempt_id}")
def get(job_id: uuid.UUID, attempt_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(service.owned(db, current_user.id, job_id, attempt_id)))


@router.get("/{attempt_id}/attachments/{index}")
def attachment(job_id: uuid.UUID, attempt_id: uuid.UUID, index: int, db: Database, current_user: CurrentUser):
    row = handle(lambda: service.owned(db, current_user.id, job_id, attempt_id))
    if index not in (0, 1):
        raise HTTPException(404, "Attachment not found")
    item = row.snapshot["attachments"][index]
    return Response(base64.b64decode(item["data"]), media_type=item["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{item["name"]}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{attempt_id}/cancel")
def cancel(job_id: uuid.UUID, attempt_id: uuid.UUID, db: Database, current_user: CurrentUser):
    return handle(lambda: service.public(service.cancel(db, current_user.id, job_id, attempt_id)))


@router.post("/{attempt_id}/send")
def send(job_id: uuid.UUID, attempt_id: uuid.UUID, body: EmailApproval, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(service.send(db, current_user.id, job_id, attempt_id, body, settings)))
