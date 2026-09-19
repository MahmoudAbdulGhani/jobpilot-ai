"""Application record origin: manual vs email-confirmed.

Revision ID: 0ad80ddc2a00
Revises: e2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa

revision = "0ad80ddc2a00"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "applications",
        sa.Column("origin", sa.String(16), server_default="manual", nullable=False),
    )
    op.create_check_constraint(
        "ck_applications_ck_applications_origin_values",
        "applications",
        "origin IN ('manual', 'email_confirmed')",
    )


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
