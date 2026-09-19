"""Deterministic ATS/readiness reports over approved pack versions.

Revision ID: 3ef7126dbb69
Revises: a434d42b4550
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "3ef7126dbb69"
down_revision = "a434d42b4550"
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
        "ats_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey(
            "saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey(
            "application_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pack_version", sa.Integer(), nullable=False),
        sa.Column("checks", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("readiness_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_version", sa.String(16), nullable=False, server_default="ats-v1"),
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_ats_reports_owner_id", "ats_reports", ["owner_id"])
    op.create_index("ix_ats_reports_pack_id", "ats_reports", ["pack_id"])


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
