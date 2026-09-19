"""Deterministic reply classification over known reply previews.

Classification is advisory: it never changes application status. A separate
explicit confirmation applies a user-chosen status to the linked application.
"""
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationRecord, MailboxReply
from app.models.reply_classification import ReplyClassification
from app.services.application_tracking_service import STATUSES, record_status_event

CATEGORIES = ("interview", "rejection", "information_request", "offer", "other")

SIGNALS: dict[str, list[str]] = {
    "interview": ["interview", "phone screen", "schedule a call", "meet with", "video call",
                  "technical round", "next steps", "invite you", "assessment", "onsite"],
    "rejection": ["not moving forward", "decided to move", "other candidates", "unfortunately",
                  "regret", "not selected", "position has been filled", "position filled",
                  "no longer considering", "will not be moving"],
    "offer": ["offer letter", "job offer", "compensation package", "pleased to offer",
              "offer details", "congratulations"],
    "information_request": ["could you send", "could you share", "could you provide",
                            "could you confirm", "could you clarify", "please send",
                            "please share", "please provide", "need your resume",
                            "need your cv", "your availability", "request for information"],
}

SUGGESTED_STATUS = {"interview": "Interview", "offer": "Offer", "rejection": "Rejected"}


def _excerpt(text: str, limit: int = 280) -> str:
    snippet = " ".join((text or "").split())
    return snippet[:limit]


def classify_text(subject: str, preview: str) -> dict:
    combined = f"{subject or ''}\n{preview or ''}"
    lowered = combined.casefold()
    hits: dict[str, list[str]] = {}
    for category, signals in SIGNALS.items():
        matched = [signal for signal in signals if signal in lowered]
        if matched:
            hits[category] = matched
    if not hits:
        return {"category": "other", "confidence": 35,
                "evidence_excerpt": _excerpt(combined) or "No preview text available.",
                "uncertainty": "No category signals found in the subject or preview; review the message yourself.",
                "suggested_status": None}
    ranked = sorted(hits, key=lambda category: (-len(hits[category]), category))
    category = ranked[0]
    confidence = min(92, 52 + 8 * len(hits[category]) + (4 if len(hits) == 1 else 0))
    anchor = hits[category][0]
    lines = [line.strip() for line in combined.splitlines() if anchor in line.casefold() and line.strip()]
    uncertainty = "Signals point to a single category; confirm the message yourself before acting."
    if len(hits) > 1:
        uncertainty = (f"Competing signals also match: "
                       + ", ".join(f"{other} ({', '.join(hits[other][:2])})" for other in ranked[1:3])
                       + ". Review the message yourself before acting.")
        confidence = max(40, confidence - 12 * (len(hits) - 1))
    return {"category": category, "confidence": confidence,
            "evidence_excerpt": (lines[0][:280] if lines else _excerpt(combined)),
            "uncertainty": uncertainty,
            "suggested_status": SUGGESTED_STATUS.get(category)}


def _owned_reply(db: Session, owner_id: uuid.UUID, reply_id: uuid.UUID) -> MailboxReply:
    reply = db.scalar(select(MailboxReply).where(
        MailboxReply.id == reply_id, MailboxReply.owner_id == owner_id))
    if reply is None:
        raise HTTPException(404, "Reply not found")
    return reply


def classify(db: Session, owner_id: uuid.UUID, reply_id: uuid.UUID) -> ReplyClassification:
    reply = _owned_reply(db, owner_id, reply_id)
    result = classify_text(reply.subject or "", reply.preview or "")
    existing = db.scalar(select(ReplyClassification).where(
        ReplyClassification.reply_id == reply_id, ReplyClassification.owner_id == owner_id))
    if existing is None:
        existing = ReplyClassification(owner_id=owner_id, reply_id=reply_id)
        db.add(existing)
    existing.category = result["category"]
    existing.confidence = result["confidence"]
    existing.evidence_excerpt = result["evidence_excerpt"]
    existing.uncertainty = result["uncertainty"]
    existing.suggested_status = result["suggested_status"]
    db.commit()
    db.refresh(existing)
    return existing


def latest(db: Session, owner_id: uuid.UUID, reply_id: uuid.UUID):
    _owned_reply(db, owner_id, reply_id)
    return db.scalar(select(ReplyClassification).where(
        ReplyClassification.reply_id == reply_id, ReplyClassification.owner_id == owner_id))


def confirm(db: Session, owner_id: uuid.UUID, reply_id: uuid.UUID, status: str) -> ReplyClassification:
    reply = _owned_reply(db, owner_id, reply_id)
    if status not in STATUSES:
        raise HTTPException(422, "Unsupported application status")
    record = None
    if reply.job_id is not None:
        record = db.scalar(select(ApplicationRecord).where(
            ApplicationRecord.owner_id == owner_id, ApplicationRecord.job_id == reply.job_id))
    if record is None:
        raise HTTPException(
            409, "Associate the reply with a saved job that has an application record first")
    classification = db.scalar(select(ReplyClassification).where(
        ReplyClassification.reply_id == reply_id, ReplyClassification.owner_id == owner_id))
    if classification is None:
        raise HTTPException(409, "Classify the reply before confirming a status change")
    if record.status != status:
        record.status = status
        record_status_event(db, record.id, status)
    classification.status_applied = True
    classification.applied_status = status
    db.commit()
    db.refresh(classification)
    return classification
