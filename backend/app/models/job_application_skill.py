import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class JobApplicationSkill(Base, TimestampMixin):
    __tablename__ = "job_application_skills"
    __table_args__ = (UniqueConstraint("owner_id", "job_id", "analysis_id", "skill_key", name="uq_job_application_skill_selection"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("saved_jobs.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_fit_analyses.id", ondelete="CASCADE"), index=True)
    skill_key: Mapped[str] = mapped_column(String(100))
    skill: Mapped[str] = mapped_column(String(100))
    importance: Mapped[str] = mapped_column(String(16))
    job_quote: Mapped[str] = mapped_column(Text)
