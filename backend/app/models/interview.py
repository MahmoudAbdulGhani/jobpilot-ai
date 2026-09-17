import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class InterviewSession(Base, TimestampMixin):
    __tablename__ = "interview_sessions"
    __table_args__ = (UniqueConstraint("owner_id", "request_key", name="uq_interview_owner_key"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("saved_jobs.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[uuid.UUID] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64))
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    configuration: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(16))
    question_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ready")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    turns: Mapped[list] = mapped_column(JSON, default=list)
    active_operation: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class InterviewOperation(Base, TimestampMixin):
    __tablename__ = "interview_operations"
    __table_args__ = (UniqueConstraint("session_id", "request_key", name="uq_interview_operation_key"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[uuid.UUID] = mapped_column()
    request_hash: Mapped[str] = mapped_column(String(64))
    step: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
