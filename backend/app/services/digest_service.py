"""Daily digest preview from validated discovery records.

Only cache payloads that validate against the DiscoveryJob contract are used;
anything else is counted as skipped, never repaired or displayed. Delivery is
disabled by default; the delivery adapter must be explicitly configured.
"""
import uuid
from datetime import datetime, timezone

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


def _valid_records(db: Session) -> tuple[list[dict], int]:
    rows = list(db.scalars(select(DiscoveryCache).order_by(
        DiscoveryCache.refreshed_at.desc().nulls_last())))
    valid: list[dict] = []
    skipped = 0
    for row in rows:
        try:
            job = DiscoveryJob.model_validate(row.payload or {})
        except ValidationError:
            skipped += 1
            continue
        if job.source not in SOURCES:
            skipped += 1
            continue
        valid.append({"job": job, "refreshed_at": row.refreshed_at})
        if len(valid) >= PREVIEW_LIMIT:
            break
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
    valid, skipped = _valid_records(db)
    items = [{"source": SOURCES[entry["job"].source], "external_id": entry["job"].external_id,
              "title": entry["job"].title, "company": entry["job"].company,
              "location": entry["job"].location, "source_url": entry["job"].source_url,
              "published_at": entry["job"].published_at, "salary": entry["job"].salary,
              "workplace_model": entry["job"].workplace_model,
              "applicant_region": entry["job"].applicant_region,
              "remote_arrangement": entry["job"].remote_arrangement,
              "test_data": entry["job"].test_data, "refreshed_at": entry["refreshed_at"]}
             for entry in valid]
    return {"generated_at": datetime.now(timezone.utc), "cadence": cadence, "items": items,
            "skipped_invalid": skipped,
            "delivery": delivery(settings)}


def send(db: Session, owner_id: uuid.UUID, settings) -> dict:
    """Deliver the current digest to the owner's account email via the adapter.

    The owner's account email is the only recipient; the adapter stays disabled
    until an explicit transport is configured. Sending must be acknowledged by
    the caller (confirm=True) at the route layer.
    """
    owner = db.get(User, owner_id)
    if owner is None or not owner.email:
        raise RuntimeError("digest_recipient_missing")
    result = preview(db, owner_id, settings)
    items = result["items"]
    if items:
        subject = f"JobPilot digest: {len(items)} validated listing(s)"
        lines = [
            f"Daily digest for {owner.email}",
            "",
            f"{len(items)} validated listing(s), {result['skipped_invalid']} invalid skipped:",
            "",
        ]
        for item in items:
            lines.append(f"- {item['title']} ({item['company']})")
            if item.get("source_url"):
                lines.append(f"  {item['source_url']}")
            if item.get("published_at"):
                lines.append(f"  published {item['published_at']}")
            if item.get("test_data"):
                lines.append("  Synthetic test listing — not a live result.")
            lines.append("")
        text = "\n".join(lines).rstrip()
        transport = digest_delivery.send(settings, owner.email, subject, text)
    else:
        subject = "JobPilot digest: no validated listings"
        digest_delivery.send(settings, owner.email, subject,
                             "No validated discovery records are cached yet.")
        transport = digest_delivery.transport(settings)
    row = preferences(db, owner_id)
    row.last_sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {"sent_at": row.last_sent_at, "recipient": owner.email, "items": len(items),
            "transport": transport, "delivery": delivery(settings)}
