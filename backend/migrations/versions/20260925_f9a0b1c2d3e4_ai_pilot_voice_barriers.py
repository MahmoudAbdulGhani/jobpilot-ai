"""Guard owner writes for the production pilot and live voice rows."""
from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION jobpilot_pilot_active_owner() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE allowed boolean;
    BEGIN
      IF pg_trigger_depth() > 1 OR NEW.owner_id IS NULL THEN RETURN NEW; END IF;
      SELECT is_active INTO allowed FROM users WHERE id=NEW.owner_id FOR UPDATE;
      IF allowed IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'Account unavailable' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON ai_pilot_dispatch FOR EACH ROW EXECUTE FUNCTION jobpilot_pilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON interview_live_voice FOR EACH ROW EXECUTE FUNCTION jobpilot_plan_active_owner()")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
