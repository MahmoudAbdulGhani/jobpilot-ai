"""Account exports, resumable deletion and inactive-owner write barriers (additive)."""
from alembic import op
import sqlalchemy as sa
revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("account_exports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archive", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("account_deletions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("receipt_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure", sa.String(64)),
        sa.Column("revocation_attempts", sa.Integer(), nullable=False),
        sa.Column("revocation_unconfirmed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("""CREATE FUNCTION jobpilot_active_owner() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE account_owner uuid; allowed boolean;
BEGIN
-- FK SET NULL actions during a deletion must remain possible.
IF pg_trigger_depth() > 1 THEN RETURN NEW; END IF;
CASE TG_TABLE_NAME
WHEN 'interview_sessions' THEN account_owner := NEW.owner_id;
WHEN 'interview_operations' THEN account_owner := (SELECT owner_id FROM interview_sessions WHERE id=NEW.session_id);
WHEN 'account_tokens' THEN account_owner := NEW.user_id;
WHEN 'application_packs' THEN account_owner := NEW.owner_id;
WHEN 'application_pack_versions' THEN account_owner := (SELECT owner_id FROM application_packs WHERE id=NEW.pack_id);
WHEN 'application_pack_operations' THEN account_owner := (SELECT owner_id FROM application_packs WHERE id=NEW.pack_id);
WHEN 'ai_usage' THEN account_owner := NEW.owner_id;
WHEN 'applications' THEN account_owner := NEW.owner_id;
WHEN 'application_status_events' THEN account_owner := (SELECT owner_id FROM applications WHERE id=NEW.application_id);
WHEN 'candidate_profiles' THEN account_owner := NEW.owner_id;
WHEN 'refresh_tokens' THEN account_owner := NEW.user_id;
WHEN 'profile_suggestion_sets' THEN account_owner := NEW.owner_id;
WHEN 'job_fit_analyses' THEN account_owner := NEW.owner_id;
WHEN 'resumes' THEN account_owner := NEW.owner_id;
WHEN 'resume_extractions' THEN account_owner := (SELECT owner_id FROM resumes WHERE id=NEW.resume_id);
WHEN 'saved_jobs' THEN account_owner := NEW.owner_id;
WHEN 'mailbox_connections' THEN account_owner := NEW.owner_id;
WHEN 'mailbox_oauth_states' THEN account_owner := NEW.owner_id;
WHEN 'email_applications' THEN account_owner := NEW.owner_id;
WHEN 'reply_syncs' THEN account_owner := NEW.owner_id;
WHEN 'mailbox_replies' THEN account_owner := NEW.owner_id;
WHEN 'account_exports' THEN account_owner := NEW.owner_id;
ELSE RAISE EXCEPTION 'Unknown ownership mapping';
END CASE;
IF account_owner IS NULL THEN RETURN NEW; END IF;
SELECT is_active INTO allowed FROM users WHERE id=account_owner FOR UPDATE;
IF allowed IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'Account unavailable' USING ERRCODE='23514'; END IF;
RETURN NEW;
END $$""")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON interview_sessions FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON interview_operations FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON account_tokens FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON application_packs FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON application_pack_versions FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON application_pack_operations FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON ai_usage FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON applications FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON application_status_events FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON candidate_profiles FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON refresh_tokens FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON profile_suggestion_sets FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON job_fit_analyses FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON resumes FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON resume_extractions FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON saved_jobs FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON mailbox_connections FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON mailbox_oauth_states FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON email_applications FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON reply_syncs FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON mailbox_replies FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON account_exports FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")
    op.execute("""CREATE FUNCTION jobpilot_no_reactivation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.is_active AND EXISTS(SELECT 1 FROM account_deletions WHERE owner_id=NEW.id) THEN
        RAISE EXCEPTION 'Account deletion accepted' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER deletion_no_reactivation BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION jobpilot_no_reactivation()")


def downgrade():
    raise RuntimeError("Account-data migration is forward-only; restore through the documented recovery procedure")
