"""In-app reminders. Never invokes a mailbox or AI provider."""
import uuid
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.api.routes.jobs import CurrentUser, Database
from app.models import ApplicationRecord, MailboxReply, SavedJob

router = APIRouter(tags=["reminders"])


class ReminderChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["create", "edit", "snooze", "complete", "cancel"]
    revision: int = Field(ge=0)
    local_time: datetime | None = None
    timezone: str = Field(default="UTC", max_length=64)
    fold: Literal[0, 1] | None = None
    confirm_terminal: bool = False

    @model_validator(mode="after")
    def valid_date(self):
        if self.action in {"create", "edit", "snooze"}:
            resolve_time(self.local_time, self.timezone, self.fold)
        return self


def resolve_time(local, zone, fold=None):
    if local is None or local.tzinfo is not None:
        raise ValueError("Supply a local date/time without an offset and an IANA timezone")
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unknown IANA timezone") from None
    candidates = [local.replace(tzinfo=tz, fold=i) for i in (0, 1)]
    try:
        valid = [d for d in candidates if d.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == local]
    except OverflowError:
        raise ValueError("Date/time is outside the supported range") from None
    if not valid:
        raise ValueError("This local time does not exist because the clocks change")
    if candidates[0].utcoffset() != candidates[1].utcoffset() and fold is None:
        raise ValueError("This time occurs twice; choose first or second occurrence")
    return candidates[fold or 0].astimezone(timezone.utc)


def public(db, record, now):
    reply = db.scalar(select(MailboxReply.id).where(
        MailboxReply.owner_id == record.owner_id, MailboxReply.job_id == record.job_id,
        MailboxReply.match_kind.in_(["reply_headers", "user_confirmed"])).limit(1))
    job = db.get(SavedJob, record.job_id)
    state = record.reminder_status or ("active" if record.follow_up_date else "none")
    return {"application_id": record.id, "job_id": record.job_id,
        "title": job.title, "company": job.company, "application_status": record.status,
        "due_at": record.follow_up_date, "timezone": record.reminder_timezone or "UTC",
        "status": state, "revision": record.reminder_revision,
        "overdue": state == "active" and bool(record.follow_up_date and record.follow_up_date <= now),
        "reply_received": reply is not None}


@router.get("/reminders")
def listing(db: Database, current_user: CurrentUser, response: Response,
            view: Literal["overdue", "upcoming", "completed", "cancelled"] = "overdue",
            after: uuid.UUID | None = None, limit: int = Query(20, ge=1, le=100)):
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    q = select(ApplicationRecord).where(ApplicationRecord.owner_id == current_user.id,
        ApplicationRecord.follow_up_date.is_not(None))
    if view in {"overdue", "upcoming"}:
        q = q.where(func.coalesce(ApplicationRecord.reminder_status, "active") == "active")
        q = q.where(ApplicationRecord.follow_up_date <= now if view == "overdue" else ApplicationRecord.follow_up_date > now)
    else:
        q = q.where(ApplicationRecord.reminder_status == view)
    if after:
        q = q.where(ApplicationRecord.id > after)
    rows = list(db.scalars(q.order_by(ApplicationRecord.id).limit(limit + 1)))
    return {"items": [public(db, r, now) for r in rows[:limit]],
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None}


def owned(db, owner, application_id, lock=False):
    q = select(ApplicationRecord).where(ApplicationRecord.id == application_id, ApplicationRecord.owner_id == owner)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    record = db.scalar(q)
    if record is None:
        raise HTTPException(404, "Application not found")
    return record


@router.get("/applications/{application_id}/reminder")
def get(application_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return public(db, owned(db, current_user.id, application_id), datetime.now(timezone.utc))


@router.post("/applications/{application_id}/reminder")
def change(application_id: uuid.UUID, body: ReminderChange, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    record = owned(db, current_user.id, application_id, True)
    now = datetime.now(timezone.utc)
    # One lifecycle per application. Repeated create can never revive or duplicate it.
    if body.action == "create" and record.follow_up_date is not None:
        return public(db, record, now)
    if body.revision != record.reminder_revision:
        raise HTTPException(409, "Reminder changed; reload before editing")
    if body.action != "create" and record.follow_up_date is None:
        raise HTTPException(409, "Create a reminder first")
    if body.action in {"create", "edit", "snooze"}:
        if record.status in {"Rejected", "Withdrawn", "Accepted", "Offer"} and not body.confirm_terminal:
            raise HTTPException(409, "Review application status and explicitly confirm scheduling")
        due = resolve_time(body.local_time, body.timezone, body.fold)
        if body.action == "snooze" and (due <= now or due <= record.follow_up_date):
            raise HTTPException(422, "Snooze must move the reminder later and into the future")
        record.follow_up_date = due
        record.reminder_timezone = body.timezone
        record.reminder_status = "active"
    else:
        record.reminder_status = "completed" if body.action == "complete" else "cancelled"
    record.reminder_revision += 1
    db.commit()
    return public(db, record, now)
