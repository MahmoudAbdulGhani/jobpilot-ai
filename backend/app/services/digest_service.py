"""Daily digest preview from validated discovery records.

Only cache payloads that validate against the DiscoveryJob contract are used;
anything else is counted as skipped, never repaired or displayed. Delivery is
structurally disabled: no delivery provider exists, so previews are for
in-app reading only.
"""
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DigestPreference, DiscoveryCache
from app.schemas.digest import DigestCadence
from app.schemas.discovery import DiscoveryJob

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


def preview(db: Session, owner_id: uuid.UUID) -> dict:
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
            "delivery": {"enabled": False,
                         "reason": "No delivery provider is configured; previews are in-app only."}}
