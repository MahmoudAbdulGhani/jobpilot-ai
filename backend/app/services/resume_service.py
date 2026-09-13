import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Resume
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
        resume_store.write_bytes(resume_id, data)
        session.commit()
    except Exception:
        session.rollback()
        resume_store.delete_bytes(resume_id)
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
    session.delete(resume)
    session.commit()
    resume_store.delete_bytes(resume.id)


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
        session.delete(resume)
    if resumes:
        session.commit()
    for resume_id in ids:
        resume_store.delete_bytes(resume_id)
    return ids