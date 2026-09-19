"""Owner data-use consents (least privilege defaults).

Revision ID: d682a8ac39ed
Revises: abf9b65a2a79
"""

from alembic import op
import sqlalchemy as sa

revision = "d682a8ac39ed"
down_revision = "abf9b65a2a79"
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
        "data_use_consents",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default="false"),
        *timestamps(),
        sa.PrimaryKeyConstraint("owner_id", "key", name="pk_data_use_consents"),
    )


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
