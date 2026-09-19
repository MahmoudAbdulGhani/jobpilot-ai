import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FollowupSuggestion(Base, TimestampMixin):
    """Persisted reminder/follow-up suggestion. Approve/reject only; never silent."""

    __tablename__ = "followup_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(
        "applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    suggested_due_at = mapped_column(DateTime(timezone=True), nullable=True)
    draft_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested")
    decided_at = mapped_column(DateTime(timezone=True), nullable=True)
