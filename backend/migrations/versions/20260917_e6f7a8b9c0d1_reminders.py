"""Add reminder lifecycle to existing follow-up dates; no data rewrite."""
from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("applications", sa.Column("reminder_status", sa.String(16), nullable=True))
    op.add_column("applications", sa.Column("reminder_timezone", sa.String(64), nullable=True))
    op.add_column("applications", sa.Column("reminder_revision", sa.Integer(), server_default="0", nullable=False))

def downgrade():
    raise RuntimeError("Reminder data must not be discarded by downgrade")
