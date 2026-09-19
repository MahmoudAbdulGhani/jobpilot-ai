import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApplicationPack(Base, TimestampMixin):
    __tablename__ = "application_packs"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_pack_owner_key"),
        Index("uq_pack_owner_generating", "owner_id", unique=True, postgresql_where=text("status = 'generating'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("saved_jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_profiles.id", ondelete="CASCADE"))
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume_extractions.id", ondelete="CASCADE"))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    source_hash: Mapped[str] = mapped_column(String(64))
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    generated: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    review_notes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    outcome_message: Mapped[str | None] = mapped_column(String(500))
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApplicationPackVersion(Base, TimestampMixin):
    __tablename__ = "application_pack_versions"
    __table_args__ = (UniqueConstraint("pack_id", "number", name="uq_pack_version_number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application_packs.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    cv: Mapped[dict[str, Any]] = mapped_column(JSON)
    cover_letter: Mapped[dict[str, Any]] = mapped_column(JSON)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)


class ApplicationPackOperation(Base):
    __tablename__ = "application_pack_operations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application_packs.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    version_number: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("pack_id", "key", name="uq_pack_operation_key"),)


class AIUsage(Base):
    """Content-free quota survives deleting generated results; removed with account."""
    __tablename__ = "ai_usage"
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    active_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
