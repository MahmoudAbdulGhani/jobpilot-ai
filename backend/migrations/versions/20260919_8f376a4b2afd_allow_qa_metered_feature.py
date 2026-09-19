"""allow qa metered feature

Revision ID: 8f376a4b2afd
Revises: a08de9e4bb9a
Create Date: 2026-09-19 14:50:36.808370

"""
from typing import Sequence, Union

from alembic import op

revision: str = '8f376a4b2afd'
down_revision: Union[str, None] = 'a08de9e4bb9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE usage_reservations DROP CONSTRAINT ck_usage_reservations_feature_allowed")
    op.execute("ALTER TABLE usage_reservations ADD CONSTRAINT ck_usage_reservations_feature_allowed "
               "CHECK (feature IN ('profile', 'fit', 'pack', 'interview', 'transcription', 'speech', 'qa'))")


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; use the documented recovery procedure")