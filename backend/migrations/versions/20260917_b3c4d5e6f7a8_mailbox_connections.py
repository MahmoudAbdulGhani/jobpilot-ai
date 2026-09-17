"""Add mailbox credentials and single-use OAuth state; existing rows untouched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("mailbox_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("capabilities", JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "subject", name="uq_mailbox_provider_subject"))
    op.create_index("ix_mailbox_connections_owner_id", "mailbox_connections", ["owner_id"])
    op.create_table("mailbox_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("verifier", sa.Text(), nullable=True),
        sa.Column("capabilities", JSONB(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("mailbox_connections.id", ondelete="CASCADE"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_mailbox_oauth_states_owner_id", "mailbox_oauth_states", ["owner_id"])


def downgrade():
    op.drop_table("mailbox_oauth_states")
    op.drop_table("mailbox_connections")
