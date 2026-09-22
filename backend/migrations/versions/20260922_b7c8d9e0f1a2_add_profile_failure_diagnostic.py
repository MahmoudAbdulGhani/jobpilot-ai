"""Add safe provider diagnostics to profile suggestion failures."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "92e7b1c6a4d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profile_suggestion_sets",
        sa.Column("failure_diagnostic", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profile_suggestion_sets", "failure_diagnostic")
