"""Plan assignments and the content-free ledger used by shared AI reservations."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class AccountPlan(Base, TimestampMixin):
    __tablename__ = "account_plans"
    __table_args__ = (CheckConstraint("base_plan IN ('free', 'legacy')", name="base_plan_allowed"),)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    base_plan: Mapped[str] = mapped_column(String(16), default="free")
    beta_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    beta_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageReservation(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (Index("ix_reservation_owner_period", "owner_id", "period_start"),
        CheckConstraint("feature IN ('profile', 'fit', 'pack', 'interview', 'transcription', 'speech')", name="feature_allowed"))
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    feature: Mapped[str] = mapped_column(String(24))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanAudit(Base):
    __tablename__ = "plan_audits"
    __table_args__ = (UniqueConstraint("owner_id", "request_key", name="uq_plan_audit_key"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    request_key: Mapped[uuid.UUID] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(24))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
