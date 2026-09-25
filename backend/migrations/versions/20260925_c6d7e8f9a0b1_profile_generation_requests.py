"""Track profile generations independently of removable resumes."""
from alembic import op
import sqlalchemy as sa

revision = "c6d7e8f9a0b1"
down_revision = "b7c8d9e0f1a2"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "profile_generation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('initial', 'refresh', 'admin', 'legacy')", name="profile_generation_kind_allowed"),
    )
    op.create_index("ix_profile_generation_owner_period", "profile_generation_requests", ["owner_id", "period_start"])
    op.create_index("ix_profile_generation_owner_source", "profile_generation_requests", ["owner_id", "source_hash"])
    op.execute("""INSERT INTO profile_generation_requests (id, owner_id, source_hash, kind, period_start, created_at)
        SELECT DISTINCT ON (owner_id, source_hash) id, owner_id, source_hash, 'legacy',
               date_trunc('month', created_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC', created_at
        FROM profile_suggestion_sets
        ORDER BY owner_id, source_hash, created_at, id""")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON profile_generation_requests FOR EACH ROW EXECUTE FUNCTION jobpilot_plan_active_owner()")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
