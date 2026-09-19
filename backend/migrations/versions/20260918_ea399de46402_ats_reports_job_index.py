"""Add ats_reports job_id index.

Revision ID: ea399de46402
Revises: 92d623f934d0
"""

from alembic import op

revision = "ea399de46402"
down_revision = "92d623f934d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_ats_reports_job_id", "ats_reports", ["job_id"], unique=False)


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")