"""Private exports and durable deletion receipts. Receipts survive user removal."""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AccountExport(Base, TimestampMixin):
    __tablename__ = "account_exports"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    session_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archive: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class AccountDeletion(Base, TimestampMixin):
    __tablename__ = "account_deletions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # No FK: this minimal receipt must outlive the account. No email or content.
    owner_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    receipt_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    failure: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revocation_attempts: Mapped[int] = mapped_column(Integer, default=0)
    revocation_unconfirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
