"""Add reviewed-import provenance and owner-scoped source identity.

Revision ID: a2b3c4d5e6f7
Revises: 9c0d1e2f3a4b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a2b3c4d5e6f7"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("saved_jobs", sa.Column("source_provider", sa.String(32), nullable=True))
    op.add_column("saved_jobs", sa.Column("source_external_id", sa.String(128), nullable=True))
    op.add_column("saved_jobs", sa.Column("source_snapshot", postgresql.JSONB(), nullable=True))
    op.add_column("saved_jobs", sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_saved_jobs_owner_source_external", "saved_jobs",
                    ["owner_id", "source_provider", "source_external_id"], unique=True)


def downgrade():
    op.drop_index("uq_saved_jobs_owner_source_external", table_name="saved_jobs")
    for name in ("imported_at", "source_snapshot", "source_external_id", "source_provider"):
        op.drop_column("saved_jobs", name)
