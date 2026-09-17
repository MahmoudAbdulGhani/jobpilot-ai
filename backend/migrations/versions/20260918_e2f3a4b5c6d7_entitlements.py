"""Add plan assignments and reservation ledger without changing existing users/usage."""
from alembic import op
import sqlalchemy as sa
revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = depends_on = None


def upgrade():
    op.create_table("account_plans",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("base_plan", sa.String(16), nullable=False),
        sa.Column("beta_expires_at", sa.DateTime(timezone=True)),
        sa.Column("beta_revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("base_plan IN ('free', 'legacy')", name="base_plan_allowed"))
    # Existing identities receive non-expiring continuity, including accounts
    # awaiting cleanup. No account/credential/usage row is rewritten.
    op.execute("INSERT INTO account_plans (owner_id, base_plan) SELECT id, 'legacy' FROM users")
    op.create_table("usage_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature", sa.String(24), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("feature IN ('profile', 'fit', 'pack', 'interview', 'transcription', 'speech')", name="feature_allowed"))
    op.create_index("ix_reservation_owner_period", "usage_reservations", ["owner_id", "period_start"])
    op.create_table("plan_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "request_key", name="uq_plan_audit_key"))
    op.create_index("ix_plan_audits_owner_id", "plan_audits", ["owner_id"])
    op.execute("""CREATE FUNCTION jobpilot_plan_active_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE allowed boolean;
    BEGIN
      IF pg_trigger_depth() > 1 THEN RETURN NEW; END IF;
      SELECT is_active INTO allowed FROM users WHERE id=NEW.owner_id FOR UPDATE;
      IF allowed IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'Account unavailable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$""")
    for table in ("account_plans", "usage_reservations", "plan_audits"):
        op.execute(f"CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION jobpilot_plan_active_owner()")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
