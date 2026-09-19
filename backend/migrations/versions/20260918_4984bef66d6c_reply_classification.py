"""Deterministic reply classifications with explicit status confirmation.

Revision ID: 4984bef66d6c
Revises: 3ef7126dbb69
"""

from alembic import op
import sqlalchemy as sa

revision = "4984bef66d6c"
down_revision = "3ef7126dbb69"
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
        "reply_classifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reply_id", sa.Uuid(), sa.ForeignKey(
            "mailbox_replies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("uncertainty", sa.Text(), nullable=False, server_default=""),
        sa.Column("suggested_status", sa.String(16), nullable=True),
        sa.Column("status_applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("applied_status", sa.String(16), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("reply_id", name="uq_reply_classification_reply"),
    )
    op.create_index("ix_reply_classifications_owner_id", "reply_classifications", ["owner_id"])
    op.create_index("ix_reply_classifications_reply_id", "reply_classifications", ["reply_id"])


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
