"""One claimed live voice conversation per interview session."""
from alembic import op
import sqlalchemy as sa

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "interview_live_voice",
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_turns", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_interview_live_voice_owner_id", "interview_live_voice", ["owner_id"])


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
