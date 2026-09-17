"""Add shared bounded public discovery cache; no owner records changed."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("discovery_cache",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError("Forward-only migration; use the documented isolated recovery procedure")
