import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Resume, ResumeExtraction
from app.schemas.resumes import ResumeUpdate
from app.services import resume_store


def create_resume(
    session: Session,
    *,
    owner_id: uuid.UUID,
    original_filename: str,
    display_name: str,
    file_extension: str,
    size_bytes: int,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> Resume:
    resume = Resume(
        owner_id=owner_id,
        original_filename=original_filename,
        display_name=display_name,
        file_extension=file_extension,
        size_bytes=size_bytes,
    )
    session.add(resume)
    session.flush()
    resume_id = resume.id
    try:
        resume_store.write_bytes(resume_id, data, content_type=content_type)
        session.commit()
    except Exception:
        session.rollback()
        try:
            resume_store.delete_bytes(resume_id)
        except Exception:
            pass  # Original failure survives; inventory identifies possible orphans.
        raise
    session.refresh(resume)
    return resume


def list_resumes(session: Session, *, owner_id: uuid.UUID) -> list[Resume]:
    return list(
        session.scalars(
            select(Resume)
            .where(Resume.owner_id == owner_id)
            .order_by(
                Resume.is_primary.desc(),
                Resume.created_at.desc(),
                Resume.id.desc(),
            )
        )
    )


def get_resume(
    session: Session, *, owner_id: uuid.UUID, resume_id: uuid.UUID
) -> Resume | None:
    return session.scalar(
        select(Resume).where(
            Resume.id == resume_id, Resume.owner_id == owner_id
        )
    )


def get_extraction(session: Session, *, resume_id: uuid.UUID) -> ResumeExtraction | None:
    return session.scalar(
        select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id)
    )


def lock_resume(session: Session, *, resume_id: uuid.UUID) -> None:
    session.execute(
        select(Resume.id).where(Resume.id == resume_id).with_for_update()
    ).scalar_one()


def update_resume(
    session: Session, *, resume: Resume, owner_id: uuid.UUID, data: ResumeUpdate
) -> Resume:
    values = data.model_dump(exclude_unset=True)
    if values.get("is_primary") is True:
        session.execute(
            update(Resume)
            .where(Resume.owner_id == owner_id, Resume.id != resume.id)
            .values(is_primary=False)
        )
    for field, value in values.items():
        setattr(resume, field, value)
    session.commit()
    session.refresh(resume)
    return resume


def delete_resume(session: Session, *, resume: Resume) -> None:
    from app.services.profile_suggestion_service import mark_source_unavailable
    resume_store.delete_bytes(resume.id)
    mark_source_unavailable(session, owner_id=resume.owner_id, resume_id=resume.id)
    session.delete(resume)
    session.commit()


def delete_owned_resumes(
    session: Session, *, owner_id: uuid.UUID
) -> list[uuid.UUID]:
    resumes = list(
        session.scalars(
            select(Resume).where(Resume.owner_id == owner_id)
        )
    )
    ids = [resume.id for resume in resumes]
    for resume in resumes:
        resume_store.delete_bytes(resume.id)
        from app.services.profile_suggestion_service import mark_source_unavailable
        mark_source_unavailable(session, owner_id=owner_id, resume_id=resume.id)
        session.delete(resume)
    if resumes:
        session.commit()
    return ids
