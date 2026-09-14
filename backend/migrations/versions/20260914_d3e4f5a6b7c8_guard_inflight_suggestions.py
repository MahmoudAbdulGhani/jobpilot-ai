"""guard in-flight suggestions

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_profile_suggestion_sets_generating",
        "profile_suggestion_sets",
        ["owner_id", "resume_id"],
        unique=True,
        postgresql_where=sa.text("status = 'generating'"),
    )


def downgrade() -> None:
    op.drop_index("uq_profile_suggestion_sets_generating", table_name="profile_suggestion_sets")
