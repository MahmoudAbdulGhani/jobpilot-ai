"""Teach the ownership barrier about advisory tables.

Revision ID: 92d623f934d0
Revises: 2de71a21aab7
"""

from alembic import op

revision = "92d623f934d0"
down_revision = "2de71a21aab7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE OR REPLACE FUNCTION jobpilot_active_owner() RETURNS trigger LANGUAGE plpgsql AS $$
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
WHEN 'job_rankings' THEN account_owner := NEW.owner_id;
WHEN 'ats_reports' THEN account_owner := NEW.owner_id;
WHEN 'reply_classifications' THEN account_owner := NEW.owner_id;
WHEN 'followup_suggestions' THEN account_owner := NEW.owner_id;
WHEN 'data_use_consents' THEN account_owner := NEW.owner_id;
WHEN 'digest_preferences' THEN account_owner := NEW.owner_id;
ELSE RAISE EXCEPTION 'Unknown ownership mapping';
END CASE;
IF account_owner IS NULL THEN RETURN NEW; END IF;
SELECT is_active INTO allowed FROM users WHERE id=account_owner FOR UPDATE;
IF allowed IS DISTINCT FROM TRUE THEN RAISE EXCEPTION 'Account unavailable' USING ERRCODE='23514'; END IF;
RETURN NEW;
END $$""")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
