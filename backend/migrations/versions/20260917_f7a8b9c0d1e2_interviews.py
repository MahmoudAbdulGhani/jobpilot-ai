"""Add private interview sessions and deduplicated model operations."""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("interview_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False), sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False), sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("turns", sa.JSON(), nullable=False), sa.Column("active_operation", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "request_key", name="uq_interview_owner_key"))
    op.create_index("ix_interview_sessions_owner_id", "interview_sessions", ["owner_id"])
    op.create_index("ix_interview_sessions_job_id", "interview_sessions", ["job_id"])
    op.create_table("interview_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=True), sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "request_key", name="uq_interview_operation_key"))
    op.create_index("ix_interview_operations_session_id", "interview_operations", ["session_id"])


def downgrade():
    raise RuntimeError("Interview snapshots and answers must not be discarded by downgrade")
