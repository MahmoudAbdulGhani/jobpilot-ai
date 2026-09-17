import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ReplySync(Base, TimestampMixin):
    __tablename__ = "reply_syncs"
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_applications.id", ondelete="CASCADE"), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailbox_connections.id", ondelete="CASCADE"), index=True)
    progress: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(64), default="not_started")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MailboxReply(Base, TimestampMixin):
    __tablename__ = "mailbox_replies"
    __table_args__ = (UniqueConstraint("mailbox_id", "message_id", name="uq_reply_mailbox_message"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailbox_connections.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_applications.id", ondelete="CASCADE"), index=True)
    suggested_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("saved_jobs.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("saved_jobs.id", ondelete="SET NULL"), index=True, nullable=True)
    message_id: Mapped[str] = mapped_column(String(255))
    thread_id: Mapped[str] = mapped_column(String(255))
    rfc_message_id: Mapped[str] = mapped_column(String(512), default="")
    match_kind: Mapped[str] = mapped_column(String(32))
    sender: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(512))
    preview: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
