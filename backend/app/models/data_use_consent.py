import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DataUseConsent(Base, TimestampMixin):
    """Owner consent posture per optional data use. Least privilege by default."""

    __tablename__ = "data_use_consents"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false")
