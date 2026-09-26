"""Store user-confirmed skills for one job and fit analysis."""
from alembic import op
import sqlalchemy as sa

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "job_application_skills",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("saved_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("job_fit_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_key", sa.String(100), nullable=False),
        sa.Column("skill", sa.String(100), nullable=False),
        sa.Column("importance", sa.String(16), nullable=False),
        sa.Column("job_quote", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "job_id", "analysis_id", "skill_key", name="uq_job_application_skill_selection"),
    )
    for column in ("owner_id", "job_id", "analysis_id"):
        op.create_index(f"ix_job_application_skills_{column}", "job_application_skills", [column])
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON job_application_skills FOR EACH ROW EXECUTE FUNCTION jobpilot_plan_active_owner()")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
