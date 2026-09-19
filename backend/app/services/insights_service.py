"""Unified owner-scoped insights over the customer's own data.

Read-only aggregation. Previews and notes are excerpted and sender addresses
are reduced to their domain so the payload stays safe to display and log.
"""
import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (ApplicationRecord, InterviewSession, JobFitAnalysis,
                        MailboxReply, SavedJob)


def _titles(db: Session, owner_id: uuid.UUID) -> dict[str, dict]:
    rows = db.scalars(select(SavedJob).where(SavedJob.owner_id == owner_id))
    return {str(job.id): {"title": job.title, "company": job.company} for job in rows}


def _excerpt(text: str | None, limit: int = 200) -> str:
    snippet = " ".join((text or "").split())
    return snippet[:limit]


def _domain(sender: str | None) -> str:
    address = (sender or "").strip()
    if "@" in address:
        return "***@" + address.rsplit("@", 1)[1][:64]
    return "***"


def build(db: Session, owner_id: uuid.UUID) -> dict:
    now = datetime.now(timezone.utc)
    jobs = _titles(db, owner_id)

    analyses = list(db.scalars(select(JobFitAnalysis).where(
        JobFitAnalysis.owner_id == owner_id, JobFitAnalysis.status == "ready").order_by(
        JobFitAnalysis.created_at.desc()).limit(200)))
    fit_counts: Counter = Counter()
    fit_gaps: list[dict] = []
    for analysis in analyses:
        result = analysis.result or {}
        for requirement in result.get("requirements", [])[:50]:
            assessment = requirement.get("assessment", "unspecified")
            fit_counts[assessment] += 1
            if assessment in {"not_evidenced", "needs_clarification"} and len(fit_gaps) < 8:
                info = jobs.get(str(analysis.job_id), {})
                fit_gaps.append({"job_id": analysis.job_id,
                                 "job_title": info.get("title", "Saved job"),
                                 "assessment": assessment,
                                 "requirement": _excerpt(requirement.get("text", ""), 160),
                                 "link": {"label": "Open saved job",
                                          "href": f"/jobs/{analysis.job_id}"}})

    applications = list(db.scalars(select(ApplicationRecord).where(
        ApplicationRecord.owner_id == owner_id).order_by(
        ApplicationRecord.created_at.desc()).limit(200)))
    application_counts: Counter = Counter()
    application_items: list[dict] = []
    for record in applications:
        application_counts[record.status] += 1
        if len(application_items) < 8:
            info = jobs.get(str(record.job_id), {})
            application_items.append({"job_id": record.job_id,
                                      "job_title": info.get("title", "Saved job"),
                                      "status": record.status, "origin": record.origin or "manual",
                                      "link": {"label": "Open saved job",
                                               "href": f"/jobs/{record.job_id}"}})

    replies = list(db.scalars(select(MailboxReply).where(
        MailboxReply.owner_id == owner_id).order_by(
        MailboxReply.received_at.desc()).limit(100)))
    reply_counts: Counter = Counter()
    reply_items: list[dict] = []
    for reply in replies:
        reply_counts[reply.match_kind] += 1
        if len(reply_items) < 8:
            job_id = reply.job_id or reply.suggested_job_id
            reply_items.append({"reply_id": reply.id, "job_id": reply.job_id,
                                "sender_domain": _domain(reply.sender),
                                "excerpt": _excerpt(reply.preview),
                                "link": ({"label": "Open saved job", "href": f"/jobs/{job_id}"}
                                         if job_id else None)})

    due = [record for record in applications
           if record.follow_up_date is not None and (record.reminder_status or "active") == "active"]
    overdue = [record for record in due if record.follow_up_date and record.follow_up_date <= now]
    reminder_items: list[dict] = []
    for record in sorted(due, key=lambda item: item.follow_up_date or now)[:8]:
        info = jobs.get(str(record.job_id), {})
        reminder_items.append({"application_id": record.id, "job_id": record.job_id,
                               "job_title": info.get("title", "Saved job"),
                               "due_at": record.follow_up_date,
                               "overdue": bool(record.follow_up_date and record.follow_up_date <= now),
                               "link": {"label": "Open reminders", "href": "/reminders"}})

    sessions = list(db.scalars(select(InterviewSession).where(
        InterviewSession.owner_id == owner_id).order_by(
        InterviewSession.created_at.desc()).limit(100)))
    interview_counts: Counter = Counter()
    interview_items: list[dict] = []
    for session in sessions:
        interview_counts[session.status] += 1
        if len(interview_items) < 8:
            interview_items.append({"session_id": session.id, "job_id": session.job_id,
                                    "status": session.status,
                                    "link": {"label": "Open interview",
                                             "href": f"/interviews/{session.id}"}})

    return {"fit_gaps": fit_gaps, "fit_counts": dict(fit_counts),
            "applications": application_items, "application_counts": dict(application_counts),
            "replies": reply_items, "reply_counts": dict(reply_counts),
            "reminders": reminder_items,
            "reminder_counts": {"overdue": len(overdue), "upcoming": len(due) - len(overdue)},
            "interviews": interview_items, "interview_counts": dict(interview_counts)}
