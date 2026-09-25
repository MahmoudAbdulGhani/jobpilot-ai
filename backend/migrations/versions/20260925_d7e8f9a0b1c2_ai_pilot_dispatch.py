"""Durable single-use AI profile pilot dispatch gate."""
from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "ai_pilot_dispatch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(20), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("INSERT INTO ai_pilot_dispatch (id) VALUES (1)")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
