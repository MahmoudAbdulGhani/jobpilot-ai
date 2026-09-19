"""Server-backed data-use matrix with least-privilege consent defaults.

The matrix states, per data domain, which fields are used, for what purpose,
which provider (if any) receives them, how long they are retained, and the
owner's consent state. Optional AI uses default to denied; core storage rows
are required and cannot be toggled. New advisory features (ranking, readiness,
classification, suggestions, insights, Q&A, digest) are local-only and never
send data to a provider.
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import MailboxConnection
from app.models.data_use_consent import DataUseConsent

OPTIONAL_KEYS = {
    "ai_profile_suggestions": "Confirmed CV text sent to the AI provider for profile suggestions.",
    "ai_job_fit": "Saved job description and profile facts sent to the AI provider for fit analysis.",
    "ai_application_packs": "Confirmed CV text and profile facts sent to the pack provider for drafts.",
    "ai_qa": "Retrieved field excerpts sent to the AI provider for natural-language answers.",
}


def _consents(db: Session, owner_id: uuid.UUID) -> dict[str, bool]:
    rows = db.scalars(select(DataUseConsent).where(DataUseConsent.owner_id == owner_id))
    return {row.key: row.allowed for row in rows}


def is_consented(db: Session, owner_id: uuid.UUID, key: str) -> bool:
    return bool(_consents(db, owner_id).get(key, False))


def _ai_provider(settings: Settings) -> str:
    if not settings.JOBPILOT_AI_ENABLED:
        return "disabled (AI off)"
    return f"{settings.JOBPILOT_AI_PROVIDER}/{settings.JOBPILOT_AI_MODEL}"


def matrix(db: Session, owner_id: uuid.UUID, settings: Settings) -> list[dict]:
    consents = _consents(db, owner_id)
    mailbox = db.scalar(select(MailboxConnection.id).where(
        MailboxConnection.owner_id == owner_id).limit(1)) is not None
    pack_provider = ("disabled (packs off)" if not settings.JOBPILOT_AI_ENABLED
                     else f"{settings.JOBPILOT_PACK_PROVIDER}/{settings.JOBPILOT_PACK_MODEL}")
    return [
        {"domain": "profile", "fields_used": ["headline", "location", "skills", "experience",
                                              "education", "languages", "target roles",
                                              "remote preference", "work authorization"],
         "used_for": ["local ranking", "readiness checks", "insights", "read-only Q&A",
                      "fit analysis (only with consent)"],
         "provider": "local-only", "retention": "until account deletion",
         "consent_key": None, "required": True, "allowed": True, "managed_by": "always"},
        {"domain": "confirmed CV text",
         "fields_used": ["confirmed extraction text", "source snapshot", "content hash"],
         "used_for": ["profile suggestions (only with consent)", "application packs (only with consent)"],
         "provider": _ai_provider(settings), "retention": "until the resume is deleted",
         "consent_key": "ai_profile_suggestions", "required": False,
         "allowed": consents.get("ai_profile_suggestions", False), "managed_by": "toggle"},
        {"domain": "selected job",
         "fields_used": ["title", "company", "location", "description", "source snapshot"],
         "used_for": ["local ranking", "readiness checks", "fit analysis (only with consent)",
                      "application packs (only with consent)", "digest context"],
         "provider": "local-only, or AI provider only with consent",
         "retention": "until the job or account is deleted",
         "consent_key": "ai_job_fit", "required": False,
         "allowed": consents.get("ai_job_fit", False), "managed_by": "toggle"},
        {"domain": "pack drafts",
         "fields_used": ["confirmed CV text", "profile facts", "selected job context"],
         "used_for": ["application pack drafts (only with consent)"],
         "provider": pack_provider, "retention": "until the pack or account is deleted",
         "consent_key": "ai_application_packs", "required": False,
         "allowed": consents.get("ai_application_packs", False), "managed_by": "toggle"},
        {"domain": "mailbox data",
         "fields_used": ["Gmail message IDs", "text previews", "send/dispatch records"],
         "used_for": ["explicit reply synchronization", "reply classification (local-only)"],
         "provider": "google (only after you connect; classification itself is local-only)",
         "retention": "until revoked, dismissed, or account deletion",
         "consent_key": None, "required": False, "allowed": mailbox, "managed_by": "connection"},
        {"domain": "advisory outputs",
         "fields_used": ["rankings", "readiness reports", "classifications", "suggestions",
                         "insights", "digest previews"],
         "used_for": ["display in your journal only"],
         "provider": "local-only", "retention": "until deleted or account deletion",
         "consent_key": None, "required": True, "allowed": True, "managed_by": "always"},
        {"domain": "saved data for Q&A answers",
         "fields_used": ["allowlisted saved fields", "retrieved matching excerpts"],
         "used_for": ["natural-language answers over your own data (only with consent)"],
         "provider": _ai_provider(settings),
         "retention": "never stored; only retrieved excerpts are sent",
         "consent_key": "ai_qa", "required": False,
         "allowed": consents.get("ai_qa", False), "managed_by": "toggle"},
    ]


def set_consent(db: Session, owner_id: uuid.UUID, key: str, allowed: bool) -> dict:
    if key not in OPTIONAL_KEYS:
        raise HTTPException(422, "This data use is managed elsewhere, not by toggle")
    row = db.get(DataUseConsent, (owner_id, key))
    if row is None:
        row = DataUseConsent(owner_id=owner_id, key=key, allowed=allowed)
        db.add(row)
    else:
        row.allowed = allowed
    db.commit()
    db.refresh(row)
    return {"key": row.key, "allowed": row.allowed,
            "detail": OPTIONAL_KEYS[key]}
