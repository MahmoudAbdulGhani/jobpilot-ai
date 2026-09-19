import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ApplicationPack, ApplicationPackVersion, SavedJob
from app.models.application_tracking import ApplicationRecord, ApplicationStatusEvent
from app.services.application_pack_service import PackError

STATUSES = {"Applied", "Interview", "Offer", "Accepted", "Rejected", "Withdrawn"}
METHODS = {"email", "employer_website", "linkedin_manual", "other"}


def owned_job(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID):
    job = db.scalar(select(SavedJob).where(
        SavedJob.id == job_id, SavedJob.owner_id == owner_id))
    if job is None:
        raise PackError(404, "Job not found")
    return job


def get_record(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, app_id: uuid.UUID):
    app = db.scalar(select(ApplicationRecord).where(ApplicationRecord.id == app_id,
                    ApplicationRecord.owner_id == owner_id, ApplicationRecord.job_id == job_id))
    if app is None:
        raise PackError(404, "Application record not found")
    return app


def get_owned_record(db: Session, owner_id: uuid.UUID, app_id: uuid.UUID):
    app = db.scalar(select(ApplicationRecord).where(
        ApplicationRecord.id == app_id, ApplicationRecord.owner_id == owner_id))
    if app is None:
        raise PackError(404, "Application record not found")
    return app


def record_status_event(db: Session, application_id: uuid.UUID, status: str) -> None:
    existing = db.scalar(select(ApplicationStatusEvent).where(
        ApplicationStatusEvent.application_id == application_id, ApplicationStatusEvent.status == status))
    if existing:
        return
    try:
        db.add(ApplicationStatusEvent(application_id=application_id,
               status=status, changed_at=datetime.now(timezone.utc)))
        db.flush()
    except IntegrityError:
        db.rollback()


def _validate_pack(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, pack_id: uuid.UUID | None, pack_version: int | None):
    if not pack_id:
        return None, None
    pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == pack_id,
                     ApplicationPack.owner_id == owner_id, ApplicationPack.job_id == job_id))
    if pack is None:
        raise PackError(
            404, "Approved application-pack version not found for this job")
    if pack.status != "ready":
        raise PackError(
            409, "Only approved application packs may be attached.")
    version = db.scalar(select(ApplicationPackVersion).where(ApplicationPackVersion.pack_id ==
                        pack_id, ApplicationPackVersion.number == (pack_version or pack.current_version)))
    if version is None or version.approved_at is None:
        raise PackError(
            409, "Select an approved pack version before recording the application.")
    return pack, version


def create_application(db: Session, owner_id: uuid.UUID, payload) -> ApplicationRecord:
    if payload.job_id is None:
        raise PackError(422, "job_id is required")
    owned_job(db, owner_id, payload.job_id)
    if db.scalar(select(ApplicationRecord).where(ApplicationRecord.owner_id == owner_id, ApplicationRecord.job_id == payload.job_id)):
        raise PackError(
            409, "An application record for this job already exists.")

    if payload.method not in METHODS:
        raise PackError(422, "Unsupported application method")
    if payload.status not in STATUSES:
        raise PackError(422, "Unsupported application status")

    if payload.follow_up_date is not None and payload.status in {"Rejected", "Withdrawn", "Accepted", "Offer"}:
        raise PackError(409, "Record the application first, then explicitly confirm a reminder using its controls")

    pack, version = _validate_pack(
        db, owner_id, payload.job_id, payload.pack_id, payload.pack_version)
    snapshot = None
    if pack and version:
        snapshot = {"cv": version.cv, "cover_letter": version.cover_letter}

    app = ApplicationRecord(
        owner_id=owner_id,
        job_id=payload.job_id,
        submission_date=payload.submission_date,
        method=payload.method,
        notes=payload.notes,
        status=payload.status,
        origin="manual",
        follow_up_date=payload.follow_up_date,
        pack_id=payload.pack_id,
        pack_version=payload.pack_version or (
            version.number if version else None),
        cv_snapshot=snapshot["cv"] if snapshot else None,
        cover_letter_snapshot=snapshot["cover_letter"] if snapshot else None,
    )
    try:
        db.add(app)
        db.commit()
        db.refresh(app)
    except IntegrityError:
        db.rollback()
        raise PackError(
            409, "An application record for this job already exists.") from None
    record_status_event(db, app.id, app.status)
    db.commit()
    return app


def update_application(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, app_id: uuid.UUID, payload) -> ApplicationRecord:
    app = get_record(db, owner_id, job_id, app_id)
    app = db.scalar(select(ApplicationRecord).where(
        ApplicationRecord.id == app.id, ApplicationRecord.owner_id == owner_id,
        ApplicationRecord.job_id == job_id).with_for_update().execution_options(populate_existing=True))
    if app is None:
        raise PackError(404, "Application not found")
    updated = False
    if payload.follow_up_date is not None and payload.follow_up_date != app.follow_up_date and (payload.status or app.status) in {"Rejected", "Withdrawn", "Accepted", "Offer"}:
        raise PackError(409, "Use the reminder controls to explicitly confirm scheduling")
    if payload.follow_up_date is not None and app.reminder_revision > 0 and payload.follow_up_date != app.follow_up_date:
        raise PackError(409, "Use the reminder controls to change this follow-up")
    for field in ["submission_date", "method", "notes", "follow_up_date", "pack_id", "pack_version"]:
        if getattr(payload, field, None) is not None:
            setattr(app, field, getattr(payload, field))
            updated = True
    if payload.pack_id or payload.pack_version:
        pack, version = _validate_pack(
            db, owner_id, app.job_id, payload.pack_id or app.pack_id, payload.pack_version or app.pack_version)
        if pack and version:
            app.pack_id = pack.id
            app.pack_version = version.number
            app.cv_snapshot = version.cv
            app.cover_letter_snapshot = version.cover_letter
            updated = True
    if payload.status:
        if payload.status not in STATUSES:
            raise PackError(422, "Unsupported application status")
        if app.status != payload.status:
            app.status = payload.status
            updated = True
            record_status_event(db, app.id, payload.status)
    if updated:
        db.commit()
    return app


def list_all_applications(db: Session, owner_id: uuid.UUID, page: int, page_size: int, status: str | None, job_id: uuid.UUID | None) -> dict:
    query = select(ApplicationRecord).where(
        ApplicationRecord.owner_id == owner_id)
    if status:
        query = query.where(ApplicationRecord.status == status)
    if job_id:
        query = query.where(ApplicationRecord.job_id == job_id)

    total_query = select(ApplicationRecord).where(
        ApplicationRecord.owner_id == owner_id)
    if status:
        total_query = total_query.where(ApplicationRecord.status == status)
    if job_id:
        total_query = total_query.where(ApplicationRecord.job_id == job_id)
    total = len(db.scalars(total_query.order_by(
        ApplicationRecord.created_at.desc(), ApplicationRecord.id.desc())).all())

    items = db.scalars(query.order_by(ApplicationRecord.created_at.desc(
    ), ApplicationRecord.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"items": list(items), "total": total, "page": page, "page_size": page_size}


def list_applications(db: Session, owner_id: uuid.UUID, page: int, page_size: int, status: str | None, job_id: uuid.UUID | None) -> dict:
    return list_all_applications(db, owner_id, page, page_size, status, job_id)


def get_application(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, app_id: uuid.UUID):
    return get_record(db, owner_id, job_id, app_id)


def delete_application(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, app_id: uuid.UUID):
    app = get_record(db, owner_id, job_id, app_id)
    db.delete(app)
    db.commit()


def list_events(db: Session, owner_id: uuid.UUID, job_id: uuid.UUID, app_id: uuid.UUID):
    app = get_record(db, owner_id, job_id, app_id)
    events = db.scalars(select(ApplicationStatusEvent).where(
        ApplicationStatusEvent.application_id == app.id).order_by(ApplicationStatusEvent.changed_at.desc()))
    return list(events)
