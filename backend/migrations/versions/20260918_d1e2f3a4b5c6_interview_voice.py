"""Speech dispatch receipts and expiring transcript drafts; additive only."""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = depends_on = None


def upgrade():
    op.create_table("interview_voice_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(64)),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON()),
        sa.Column("transcript", sa.Text()),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "request_key", name="uq_voice_owner_key"))
    for column in ("owner_id", "session_id"):
        op.create_index("ix_interview_voice_operations_" + column, "interview_voice_operations", [column])
    op.execute("""CREATE FUNCTION jobpilot_voice_active_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE allowed boolean; session_owner uuid;
    BEGIN
      SELECT is_active INTO allowed FROM users WHERE id=NEW.owner_id FOR UPDATE;
      SELECT owner_id INTO session_owner FROM interview_sessions WHERE id=NEW.session_id;
      IF allowed IS DISTINCT FROM TRUE OR session_owner IS DISTINCT FROM NEW.owner_id THEN
        RAISE EXCEPTION 'Account or session unavailable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON interview_voice_operations FOR EACH ROW EXECUTE FUNCTION jobpilot_voice_active_owner()")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
