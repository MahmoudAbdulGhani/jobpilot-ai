import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DigestPreference(Base, TimestampMixin):
    """Digest cadence preference. Delivery stays disabled without a provider."""

    __tablename__ = "digest_preferences"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    cadence: Mapped[str] = mapped_column(String(16), nullable=False, default="off")
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
