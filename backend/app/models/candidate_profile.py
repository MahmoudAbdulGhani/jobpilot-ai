import uuid
from typing import Any

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CandidateProfile(Base, TimestampMixin):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_roles: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    remote_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    work_authorization: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skills: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    experience: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    languages: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    salary_preference: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    ai_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
