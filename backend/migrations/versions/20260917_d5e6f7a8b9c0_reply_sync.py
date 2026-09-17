"""Add bounded reply synchronization progress and owner-scoped reply previews."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("reply_syncs",
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("email_applications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("mailbox_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("progress", JSONB(), nullable=False), sa.Column("status", sa.String(64), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)), sa.Column("retry_after", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("mailbox_replies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("mailbox_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("email_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggested_job_id", sa.Uuid(), sa.ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("saved_jobs.id", ondelete="SET NULL")),
        sa.Column("message_id", sa.String(255), nullable=False), sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("rfc_message_id", sa.String(512), nullable=False), sa.Column("match_kind", sa.String(32), nullable=False),
        sa.Column("sender", sa.String(512), nullable=False), sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("preview", sa.Text(), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("mailbox_id", "message_id", name="uq_reply_mailbox_message"))
    for table, columns in (("reply_syncs", ["owner_id", "mailbox_id"]),
                           ("mailbox_replies", ["owner_id", "mailbox_id", "attempt_id", "suggested_job_id", "job_id"])):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    op.drop_table("mailbox_replies")
    op.drop_table("reply_syncs")
