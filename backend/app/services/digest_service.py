"""Daily digest preview from validated discovery records.

Only cache payloads that validate against the DiscoveryJob contract are used;
anything else is counted as skipped, never repaired or displayed. Delivery is
disabled by default; the delivery adapter must be explicitly configured.
"""
import uuid
import hashlib
import json
import jwt
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from fastapi import HTTPException

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DigestPreference, DiscoveryCache, User
from app.schemas.digest import DigestCadence
from app.schemas.discovery import DiscoveryJob
from app.services import digest_delivery

PREVIEW_LIMIT = 20
SOURCES = {"jobtech": "JobTech JobSearch", "jobicy": "Jobicy"}


def preferences(db: Session, owner_id: uuid.UUID) -> DigestPreference:
    row = db.get(DigestPreference, owner_id)
    if row is None:
        row = DigestPreference(owner_id=owner_id, cadence="off")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def set_cadence(db: Session, owner_id: uuid.UUID, cadence: DigestCadence) -> DigestPreference:
    row = db.get(DigestPreference, owner_id)
    if row is None:
        row = DigestPreference(owner_id=owner_id, cadence=cadence)
        db.add(row)
    else:
        row.cadence = cadence
    db.commit()
    db.refresh(row)
    return row


def _valid_records(db: Session, settings) -> tuple[list[dict], int]:
    rows = list(db.scalars(select(DiscoveryCache).order_by(
        DiscoveryCache.refreshed_at.desc().nulls_last())))
    valid: list[dict] = []
    skipped = 0
    at = datetime.now(timezone.utc)
    for row in rows:
        if row.source != "jobicy" or not row.refreshed_at or not at - timedelta(hours=1) < row.refreshed_at <= at:
            skipped += 1
            continue
        payload = row.payload or {}
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list) or not isinstance(payload.get("checks", {}), dict):
            skipped += 1
            continue
        for raw in payload["jobs"][:100]:
            try:
                job = DiscoveryJob.model_validate(raw)
                checked = payload.get("checks", {}).get(job.external_id, {})
                deadline = datetime.fromisoformat(job.deadline.replace("Z", "+00:00")) if job.deadline else None
                if deadline and deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                url = urlsplit(job.source_url)
                if (job.source != row.source or (job.test_data and settings.ENVIRONMENT == "production")
                        or (deadline and deadline <= at) or not isinstance(checked, dict)
                        or checked.get("status", 200) != 200
                        or url.scheme != "https" or url.hostname != "jobicy.com"
                        or url.username or url.password or not url.path.startswith("/jobs/")):
                    raise ValueError()
            except (ValidationError, ValueError, TypeError, AttributeError):
                skipped += 1
                continue
            valid.append({"job": job, "refreshed_at": row.refreshed_at})
            if len(valid) >= PREVIEW_LIMIT:
                return valid, skipped
    return valid, skipped


def delivery(settings) -> dict:
    value = digest_delivery.transport(settings)
    if value == "disabled":
        return {"enabled": False,
                "reason": "Digest email delivery is disabled; previews are in-app only."}
    if value == "test":
        return {"enabled": True,
                "reason": "Test transport (end-to-end test mode) delivers to the in-memory sink."}
    return {"enabled": True,
            "reason": f"SMTP transport via {settings.JOBPILOT_DIGEST_SMTP_HOST}."}


def preview(db: Session, owner_id: uuid.UUID, settings) -> dict:
    cadence = preferences(db, owner_id).cadence
    valid, skipped = _valid_records(db, settings)
    items = [{"source": SOURCES[entry["job"].source], "external_id": entry["job"].external_id,
              "title": entry["job"].title, "company": entry["job"].company,
              "location": entry["job"].location, "source_url": entry["job"].source_url,
              "published_at": entry["job"].published_at, "salary": entry["job"].salary,
              "workplace_model": entry["job"].workplace_model,
              "applicant_region": entry["job"].applicant_region,
              "remote_arrangement": entry["job"].remote_arrangement,
              "test_data": entry["job"].test_data, "refreshed_at": entry["refreshed_at"]}
             for entry in valid]
    owner = db.get(User, owner_id)
    if owner is None:
        raise HTTPException(404, "Account unavailable")
    subject = f"JobPilot digest: {len(items)} validated listing(s)"
    body = "\n\n".join(
        f"{item['title']} ({item['company']})\n{item['source_url']}\nPublished: {item['published_at'] or 'unknown'}"
        + ("\nSynthetic test listing — not a live result." if item["test_data"] else "")
        for item in items) or "No validated discovery records are cached yet."
    snapshot = {"recipient": owner.email, "subject": subject, "body": body,
                "items": items, "transport": digest_delivery.transport(settings),
                "last_sent_at": preferences(db, owner_id).last_sent_at}
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
    token = jwt.encode({"purpose": "digest-review", "sub": str(owner_id), "digest": digest,
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.SECRET_KEY, algorithm="HS256")
    return {"generated_at": datetime.now(timezone.utc), "cadence": cadence, "items": items,
            "skipped_invalid": skipped,
            "delivery": delivery(settings), "recipient": owner.email, "subject": subject,
            "body": body, "preview_token": token}


def send(db: Session, owner_id: uuid.UUID, settings, preview_token: str) -> dict:
    """Deliver the current digest to the owner's account email via the adapter.

    The owner's account email is the only recipient; the adapter stays disabled
    until an explicit transport is configured. Sending must be acknowledged by
    the caller (confirm=True) at the route layer.
    """
    db.scalar(select(DigestPreference).where(DigestPreference.owner_id == owner_id).with_for_update().execution_options(populate_existing=True))
    owner = db.get(User, owner_id)
    if owner is None or not owner.email:
        raise RuntimeError("digest_recipient_missing")
    result = preview(db, owner_id, settings)
    try:
        approved = jwt.decode(preview_token, settings.SECRET_KEY, algorithms=["HS256"], options={"require": ["exp", "sub", "purpose", "digest"]})
        current = jwt.decode(result["preview_token"], settings.SECRET_KEY, algorithms=["HS256"])
        if approved["purpose"] != "digest-review" or approved["sub"] != str(owner_id) or approved["digest"] != current["digest"]:
            raise ValueError()
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(409, "Digest review expired or changed. Preview and approve it again.") from None
    items = result["items"]
    transport = digest_delivery.send(settings, result["recipient"], result["subject"], result["body"])
    row = preferences(db, owner_id)
    row.last_sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {"sent_at": row.last_sent_at, "recipient": owner.email, "items": len(items),
            "transport": transport, "delivery": delivery(settings)}
