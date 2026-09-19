import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class JobRanking(Base, TimestampMixin):
    """Deterministic cross-job ranking run. Advisory only; no provider calls."""

    __tablename__ = "job_rankings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    profile_hash: Mapped[str] = mapped_column(String(64))
    job_hashes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    engine_version: Mapped[str] = mapped_column(String(16), default="rank-v1")
