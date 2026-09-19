"""Deterministic cross-job ranking runs.

Revision ID: a434d42b4550
Revises: 0ad80ddc2a00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a434d42b4550"
down_revision = "0ad80ddc2a00"
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
        "job_rankings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("job_hashes", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("items", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("engine_version", sa.String(16), nullable=False,
                  server_default="rank-v1"),
        *timestamps(),
    )
    op.create_index("ix_job_rankings_owner_id", "job_rankings", ["owner_id"])


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
