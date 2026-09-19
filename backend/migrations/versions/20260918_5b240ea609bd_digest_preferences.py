"""Digest cadence preferences. Delivery has no provider and stays disabled.

Revision ID: 5b240ea609bd
Revises: d682a8ac39ed
"""

from alembic import op
import sqlalchemy as sa

revision = "5b240ea609bd"
down_revision = "d682a8ac39ed"
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
        "digest_preferences",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cadence", sa.String(16), nullable=False, server_default="off"),
        *timestamps(),
        sa.PrimaryKeyConstraint("owner_id", name="pk_digest_preferences"),
    )


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
