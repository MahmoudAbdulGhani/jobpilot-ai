import uuid
from typing import Literal

from fastapi import APIRouter, Response, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select

from app.api.routes.jobs import CurrentUser, Database
from app.api.routes.email_applications import handle
from app.core.config import get_settings
from app.models import EmailApplication, MailboxReply, ReplySync, SavedJob
from app.services import reply_service as service

router = APIRouter(tags=["application replies"])


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True]


class Association(SyncRequest):
    job_id: uuid.UUID | None


@router.get("/jobs/{job_id}/replies")
def listing(job_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not db.scalar(select(SavedJob.id).where(SavedJob.id == job_id, SavedJob.owner_id == current_user.id)):
        raise HTTPException(404, "Job not found")
    replies = db.scalars(select(MailboxReply).where(MailboxReply.owner_id == current_user.id,
        or_(MailboxReply.job_id == job_id, (MailboxReply.suggested_job_id == job_id) & (MailboxReply.match_kind == "uncertain_thread")))
        .order_by(MailboxReply.received_at.desc()).limit(100))
    attempts = db.scalars(select(EmailApplication).where(EmailApplication.owner_id == current_user.id,
        EmailApplication.job_id == job_id, EmailApplication.status.in_(["sent", "unknown", "sending", "simulated"])))
    syncs = []
    for attempt in attempts:
        state = db.get(ReplySync, attempt.id)
        syncs.append({"attempt_id": str(attempt.id), "provider": attempt.snapshot["provider"],
            "send_status": attempt.status, "sync": service.public_sync(state) if state else None})
    jobs = db.scalars(select(SavedJob).where(SavedJob.owner_id == current_user.id).order_by(SavedJob.created_at.desc()).limit(100))
    return {"items": [service.public_reply(r) for r in replies], "attempts": syncs,
        "jobs": [{"id": str(j.id), "title": j.title, "company": j.company} for j in jobs]}


@router.post("/jobs/{job_id}/email-applications/{attempt_id}/replies/sync")
def sync(job_id: uuid.UUID, attempt_id: uuid.UUID, body: SyncRequest, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public_sync(service.batch(db, current_user.id, job_id, attempt_id, settings)))


@router.patch("/replies/{reply_id}/association")
def correct(reply_id: uuid.UUID, body: Association, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public_reply(service.correct(db, current_user.id, reply_id, body.job_id)))
