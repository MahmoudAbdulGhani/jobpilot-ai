import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class JobFitAnalysis(Base, TimestampMixin):
    __tablename__ = "job_fit_analyses"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_job_fit_owner_key"),
        Index(
            "uq_job_fit_generating_job",
            "owner_id",
            "job_id",
            unique=True,
            postgresql_where=text("status = 'generating'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("saved_jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    job_hash: Mapped[str] = mapped_column(String(64))
    profile_hash: Mapped[str] = mapped_column(String(64))
    job_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    profile_facts: Mapped[list[Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    outcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
