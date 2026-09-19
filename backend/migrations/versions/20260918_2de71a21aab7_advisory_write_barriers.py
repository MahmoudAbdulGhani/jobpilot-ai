"""Write barriers for advisory tables (ranking, ATS, classification, suggestions, consents, digest).

Revision ID: 2de71a21aab7
Revises: 5b240ea609bd
"""

from alembic import op

revision = "2de71a21aab7"
down_revision = "5b240ea609bd"
branch_labels = None
depends_on = None

TABLES = ("job_rankings", "ats_reports", "reply_classifications",
          "followup_suggestions", "data_use_consents", "digest_preferences")


def upgrade():
    for table in TABLES:
        op.execute(f"CREATE TRIGGER account_write_barrier BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION jobpilot_active_owner()")


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")
