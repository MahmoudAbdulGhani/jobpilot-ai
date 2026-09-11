import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import SavedJob
from app.schemas.jobs import SavedJobCreate, SavedJobUpdate


def create_saved_job(
    session: Session, *, owner_id: uuid.UUID, data: SavedJobCreate
) -> SavedJob:
    values = data.model_dump(mode="json")
    job = SavedJob(owner_id=owner_id, **values)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_saved_jobs(
    session: Session,
    *,
    owner_id: uuid.UUID,
    archived: bool,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[SavedJob], int]:
    filters = [SavedJob.owner_id == owner_id, SavedJob.is_archived == archived]
    normalized_search = search.strip() if search else ""
    if normalized_search:
        escaped = _escape_like(normalized_search)
        pattern = f"%{escaped}%"
        filters.append(
            or_(
                SavedJob.title.ilike(pattern, escape="\\"),
                SavedJob.company.ilike(pattern, escape="\\"),
            )
        )

    total = session.scalar(
        select(func.count(SavedJob.id)).where(*filters)
    ) or 0
    jobs = list(
        session.scalars(
            select(SavedJob)
            .where(*filters)
            .order_by(SavedJob.created_at.desc(), SavedJob.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return jobs, total


def get_saved_job(
    session: Session, *, owner_id: uuid.UUID, job_id: uuid.UUID
) -> SavedJob | None:
    return session.scalar(
        select(SavedJob).where(
            SavedJob.id == job_id, SavedJob.owner_id == owner_id
        )
    )


def update_saved_job(
    session: Session, *, job: SavedJob, data: SavedJobUpdate
) -> SavedJob:
    values = data.model_dump(exclude_unset=True, mode="json")
    for field, value in values.items():
        setattr(job, field, value)
    session.commit()
    session.refresh(job)
    return job


def delete_saved_job(session: Session, *, job: SavedJob) -> None:
    session.delete(job)
    session.commit()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
