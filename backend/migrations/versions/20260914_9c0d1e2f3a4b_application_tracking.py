"""Application tracking records, job status history, and pack snapshots.

Revision ID: 9c0d1e2f3a4b
Revises: f5a6b7c8d9e0
"""

from alembic import op
import sqlalchemy as sa

revision = "9c0d1e2f3a4b"
down_revision = "f5a6b7c8d9e0"
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
        "applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey(
            "saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_date", sa.DateTime(
            timezone=True), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("follow_up_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey(
            "application_packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pack_version", sa.Integer(), nullable=True),
        sa.Column("cv_snapshot", sa.JSON(), nullable=True),
        sa.Column("cover_letter_snapshot", sa.JSON(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("owner_id", "job_id", name="uq_app_owner_job"),
    )
    op.create_index("ix_applications_owner_id", "applications", ["owner_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])

    op.create_table(
        "application_status_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey(
            "applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("application_id", "status",
                            name="uq_application_status_event"),
    )
    op.create_index("ix_application_status_events_application_id",
                    "application_status_events", ["application_id"])


def downgrade():
    op.drop_index("ix_application_status_events_application_id",
                  table_name="application_status_events")
    op.drop_table("application_status_events")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_index("ix_applications_owner_id", table_name="applications")
    op.drop_table("applications")
