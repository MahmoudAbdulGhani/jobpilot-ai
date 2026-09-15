import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApplicationRecord(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("owner_id", "job_id", name="uq_app_owner_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(
        "saved_jobs.id", ondelete="CASCADE"), index=True)
    submission_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    follow_up_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    pack_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(
        "application_packs.id", ondelete="SET NULL"), nullable=True)
    pack_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_snapshot: Mapped[dict[str, Any] |
                        None] = mapped_column(JSON, nullable=True)
    cover_letter_snapshot: Mapped[dict[str, Any]
                                  | None] = mapped_column(JSON, nullable=True)


class ApplicationStatusEvent(Base, TimestampMixin):
    __tablename__ = "application_status_events"
    __table_args__ = (
        UniqueConstraint("application_id", "status",
                         name="uq_application_status_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
