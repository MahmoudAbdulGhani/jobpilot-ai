"""Reminder and follow-up suggestions from application age and reply state.

Suggestions are persisted drafts. Approving a reminder suggestion creates the
reminder through the same guards as the reminder controls; approving a message
suggestion only marks the draft approved for the user to copy. Nothing is ever
created or sent silently.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApplicationRecord, MailboxReply, SavedJob
from app.models.followup_suggestion import FollowupSuggestion

ELIGIBLE_STATUSES = {"Applied", "Interview"}
ACTIVE_REMINDER = "active"


def _reply_received(db: Session, record: ApplicationRecord) -> bool:
    return db.scalar(select(MailboxReply.id).where(
        MailboxReply.owner_id == record.owner_id, MailboxReply.job_id == record.job_id,
        MailboxReply.match_kind.in_(["reply_headers", "user_confirmed"])).limit(1)) is not None


def _open_kind(db: Session, owner_id: uuid.UUID, application_id: uuid.UUID, kind: str) -> bool:
    return db.scalar(select(FollowupSuggestion.id).where(
        FollowupSuggestion.owner_id == owner_id, FollowupSuggestion.application_id == application_id,
        FollowupSuggestion.kind == kind, FollowupSuggestion.state == "suggested").limit(1)) is not None


def _reminder_due(record: ApplicationRecord, now: datetime) -> datetime:
    candidate = record.submission_date + timedelta(days=7)
    return candidate if candidate > now else now + timedelta(days=2)


def _draft_message(job: SavedJob | None) -> str:
    title = job.title if job else "the role"
    company = job.company if job else "your contact"
    return (f"Subject: Following up on my application for {title}\n\n"
            f"Hello {company} hiring team,\n\n"
            f"I applied for {title} and wanted to briefly reaffirm my interest. "
            f"Please let me know if any further material would help your review.\n\n"
            f"Draft only: copy, edit and send this yourself. JobPilot never sends it.")


def _reason(record: ApplicationRecord, age_days: int, replied: bool) -> str:
    age = f"Application is {age_days} days old (status {record.status})."
    if replied:
        return f"{age} A reply was received; consider a manual follow-up message."
    if record.follow_up_date is None:
        return f"{age} No reminder is set and no reply was received."
    return f"{age} The previous reminder is {record.reminder_status}."


def generate(db: Session, owner_id: uuid.UUID) -> list[FollowupSuggestion]:
    now = datetime.now(timezone.utc)
    records = list(db.scalars(select(ApplicationRecord).where(
        ApplicationRecord.owner_id == owner_id,
        ApplicationRecord.status.in_(ELIGIBLE_STATUSES)).order_by(ApplicationRecord.submission_date)))
    created: list[FollowupSuggestion] = []
    for record in records:
        replied = _reply_received(db, record)
        reminder_active = record.follow_up_date is not None and (record.reminder_status or "active") == ACTIVE_REMINDER
        age_days = max(0, (now - record.submission_date).days) if record.submission_date else 0
        job = db.get(SavedJob, record.job_id)
        if not reminder_active and not _open_kind(db, owner_id, record.id, "reminder"):
            created.append(FollowupSuggestion(
                owner_id=owner_id, application_id=record.id, kind="reminder",
                suggested_due_at=_reminder_due(record, now), draft_message=None,
                reason=_reason(record, age_days, replied)))
        if replied and not _open_kind(db, owner_id, record.id, "followup_message"):
            created.append(FollowupSuggestion(
                owner_id=owner_id, application_id=record.id, kind="followup_message",
                suggested_due_at=None, draft_message=_draft_message(job),
                reason=_reason(record, age_days, True)))
    for row in created:
        db.add(row)
    db.commit()
    for row in created:
        db.refresh(row)
    return created


def present(db: Session, row: FollowupSuggestion) -> dict:
    job = None
    record = db.get(ApplicationRecord, row.application_id)
    if record is not None:
        job = db.get(SavedJob, record.job_id)
    return {"id": row.id, "application_id": row.application_id,
            "job_id": job.id if job else None, "job_title": job.title if job else None,
            "company": job.company if job else None, "kind": row.kind,
            "suggested_due_at": row.suggested_due_at, "draft_message": row.draft_message,
            "reason": row.reason, "state": row.state, "decided_at": row.decided_at,
            "created_at": row.created_at, "updated_at": row.updated_at}


def listing(db: Session, owner_id: uuid.UUID, state: str | None, page: int, page_size: int) -> dict:
    query = select(FollowupSuggestion).where(FollowupSuggestion.owner_id == owner_id)
    if state:
        if state not in {"suggested", "approved", "rejected"}:
            raise HTTPException(422, "Unsupported suggestion state")
        query = query.where(FollowupSuggestion.state == state)
    total = db.scalar(select(func.count()).select_from(FollowupSuggestion).where(
        FollowupSuggestion.owner_id == owner_id,
        *( [FollowupSuggestion.state == state] if state else []))) or 0
    rows = list(db.scalars(query.order_by(FollowupSuggestion.created_at.desc(),
                                          FollowupSuggestion.id.desc()).offset(
        (page - 1) * page_size).limit(page_size)))
    return {"items": [present(db, row) for row in rows], "total": total, "page": page, "page_size": page_size}


def _owned(db: Session, owner_id: uuid.UUID, suggestion_id: uuid.UUID) -> FollowupSuggestion:
    row = db.scalar(select(FollowupSuggestion).where(
        FollowupSuggestion.id == suggestion_id, FollowupSuggestion.owner_id == owner_id))
    if row is None:
        raise HTTPException(404, "Suggestion not found")
    return row


def approve(db: Session, owner_id: uuid.UUID, suggestion_id: uuid.UUID) -> dict:
    row = _owned(db, owner_id, suggestion_id)
    if row.state != "suggested":
        raise HTTPException(409, "This suggestion was already decided")
    now = datetime.now(timezone.utc)
    if row.kind == "reminder":
        record = db.scalar(select(ApplicationRecord).where(
            ApplicationRecord.id == row.application_id,
            ApplicationRecord.owner_id == owner_id).with_for_update().execution_options(
            populate_existing=True))
        if record is None:
            raise HTTPException(404, "Application not found")
        if record.follow_up_date is not None and (record.reminder_status or "active") == ACTIVE_REMINDER:
            raise HTTPException(409, "An active reminder already exists; use its controls")
        if row.suggested_due_at is None or row.suggested_due_at <= now:
            raise HTTPException(422, "The suggested time passed; choose a time with the reminder controls")
        if record.status in {"Rejected", "Withdrawn", "Accepted", "Offer"}:
            raise HTTPException(409, "Review application status and explicitly confirm scheduling")
        record.follow_up_date = row.suggested_due_at
        record.reminder_timezone = "UTC"
        record.reminder_status = "active"
        record.reminder_revision += 1
    row.state = "approved"
    row.decided_at = now
    db.commit()
    return present(db, row)


def reject(db: Session, owner_id: uuid.UUID, suggestion_id: uuid.UUID) -> dict:
    row = _owned(db, owner_id, suggestion_id)
    if row.state != "suggested":
        raise HTTPException(409, "This suggestion was already decided")
    row.state = "rejected"
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    return present(db, row)
