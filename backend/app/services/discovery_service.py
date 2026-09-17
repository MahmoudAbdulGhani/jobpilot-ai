"""Reviewed snapshots and owner-scoped persistence, separate from provider I/O."""
from datetime import datetime, timedelta, timezone

import jwt
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import SavedJob
from app.schemas.discovery import DiscoveryJob, DiscoveryResult, DiscoveryPreview
from app.schemas.jobs import SavedJobCreate
from app.services.discovery_provider import DiscoveryError


def existing_job(db, owner_id, external_id):
    return db.scalar(select(SavedJob).where(SavedJob.owner_id == owner_id,
        SavedJob.source_provider == "jobtech", SavedJob.source_external_id == external_id))


def with_duplicates(db, owner_id, jobs):
    rows = db.scalars(select(SavedJob).where(SavedJob.owner_id == owner_id,
        SavedJob.source_provider == "jobtech", SavedJob.source_external_id.in_([j.external_id for j in jobs])))
    existing = {row.source_external_id: row.id for row in rows}
    return [DiscoveryResult(**j.model_dump(), existing_job_id=existing.get(j.external_id)) for j in jobs]


def prepare_preview(db, owner_id, job, settings):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    token = jwt.encode({"sub": str(owner_id), "exp": expires_at,
        "iss": "jobpilot-discovery", "aud": "reviewed-job-import", "type": "discovery-preview",
        "job": job.model_dump(mode="json")}, settings.SECRET_KEY, algorithm="HS256")
    return DiscoveryPreview(job=with_duplicates(db, owner_id, [job])[0], preview_token=token, expires_at=expires_at)


def import_preview(db, owner_id, token, settings):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"],
            issuer="jobpilot-discovery", audience="reviewed-job-import",
            options={"require": ["exp", "sub", "type", "job"]})
        if payload["sub"] != str(owner_id) or payload["type"] != "discovery-preview":
            raise ValueError()
        source = DiscoveryJob.model_validate(payload["job"])
        values = SavedJobCreate(title=source.title, company=source.company,
            location=source.location, description=source.description, source_url=source.source_url)
    except (jwt.InvalidTokenError, ValueError, ValidationError):
        raise DiscoveryError(422, "The preview is invalid or expired. Preview the listing again.") from None
    if source.test_data and (not settings.E2E_TEST_MODE or settings.POSTGRES_DB != settings.POSTGRES_TEST_DB):
        raise DiscoveryError(422, "Synthetic listings cannot be imported outside guarded tests.")
    existing = existing_job(db, owner_id, source.external_id)
    if existing:
        return existing, True
    job = SavedJob(owner_id=owner_id, **values.model_dump(mode="json"),
        source_provider=source.source, source_external_id=source.external_id,
        source_snapshot=source.model_dump(mode="json"), imported_at=datetime.now(timezone.utc))
    try:
        # A unique database index resolves concurrent imports, including archived jobs.
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        existing = existing_job(db, owner_id, source.external_id)
        if existing:
            return existing, True
        raise
    db.commit()
    db.refresh(job)
    return job, False
