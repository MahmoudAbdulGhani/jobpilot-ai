"""Persisted follow-up suggestions with approve/reject actions.

Revision ID: abf9b65a2a79
Revises: 4984bef66d6c
"""

from alembic import op
import sqlalchemy as sa

revision = "abf9b65a2a79"
down_revision = "4984bef66d6c"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(name, sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False)
        for name in ("created_at", "updated_at")
    ]


def upgrade():
    op.create_table(
        "followup_suggestions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey(
            "applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("suggested_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("draft_message", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_followup_suggestions_owner_id", "followup_suggestions", ["owner_id"])
    op.create_index("ix_followup_suggestions_application_id", "followup_suggestions", ["application_id"])


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
