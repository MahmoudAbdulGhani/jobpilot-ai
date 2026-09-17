"""Add immutable email reviews and durable dispatch outcomes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("email_applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("raw_message", sa.LargeBinary(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("approved_hash", sa.String(64)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("dispatch_at", sa.DateTime(timezone=True)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("provider_thread_id", sa.String(255)),
        sa.Column("outcome", sa.String(100)),
        sa.Column("provider_status", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_email_applications_owner_id", "email_applications", ["owner_id"])
    op.create_index("ix_email_applications_job_id", "email_applications", ["job_id"])
    op.create_index("uq_email_active_job", "email_applications", ["owner_id", "job_id"], unique=True,
        postgresql_where=sa.text("status IN ('review','queued','sending','sent','unknown','simulated')"))
    op.execute("""CREATE FUNCTION guard_email_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.snapshot IS DISTINCT FROM OLD.snapshot OR NEW.raw_message IS DISTINCT FROM OLD.raw_message
        OR NEW.snapshot_hash IS DISTINCT FROM OLD.snapshot_hash OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
        OR NEW.job_id IS DISTINCT FROM OLD.job_id
        OR (OLD.approved_at IS NOT NULL AND (NEW.approved_at IS DISTINCT FROM OLD.approved_at
          OR NEW.approved_hash IS DISTINCT FROM OLD.approved_hash)) THEN
        RAISE EXCEPTION 'Email review snapshot and approval are immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER email_snapshot_immutable BEFORE UPDATE ON email_applications FOR EACH ROW EXECUTE FUNCTION guard_email_snapshot()")


def downgrade():
    op.drop_table("email_applications")
    op.execute("DROP FUNCTION guard_email_snapshot()")
