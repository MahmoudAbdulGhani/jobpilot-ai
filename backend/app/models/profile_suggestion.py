import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProfileSuggestionSet(Base, TimestampMixin):
    __tablename__ = "profile_suggestion_sets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resume_extractions.id", ondelete="CASCADE"))
    source_text: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    source_reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    profile_revision: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    suggestions: Mapped[list[Any] | None] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    outcome_message: Mapped[str | None] = mapped_column(String(500))
    applied_selection_hash: Mapped[str | None] = mapped_column(String(64))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apply_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
