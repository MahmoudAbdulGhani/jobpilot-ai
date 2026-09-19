import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ReplyClassification(Base, TimestampMixin):
    """Deterministic reply classification. Advisory only; never changes status."""

    __tablename__ = "reply_classifications"
    __table_args__ = (
        UniqueConstraint("reply_id", name="uq_reply_classification_reply"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reply_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(
        "mailbox_replies.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    evidence_excerpt: Mapped[str] = mapped_column(Text, default="")
    uncertainty: Mapped[str] = mapped_column(Text, default="")
    suggested_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status_applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false")
    applied_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
