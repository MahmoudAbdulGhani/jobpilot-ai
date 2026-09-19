import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AtsReport(Base, TimestampMixin):
    """Versioned deterministic readiness report over an approved pack version."""

    __tablename__ = "ats_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(
        "saved_jobs.id", ondelete="CASCADE"), index=True)
    pack_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(
        "application_packs.id", ondelete="CASCADE"), index=True)
    pack_version: Mapped[int] = mapped_column(Integer)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    readiness_score: Mapped[int] = mapped_column(Integer, default=0)
    report_version: Mapped[str] = mapped_column(String(16), default="ats-v1")
    inputs_hash: Mapped[str] = mapped_column(String(64))
