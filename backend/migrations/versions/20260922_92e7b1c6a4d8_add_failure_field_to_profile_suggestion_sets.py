"""add failure_field to profile suggestion sets

Revision ID: 92e7b1c6a4d8
Revises: ec844a9fd5fb
Create Date: 2026-09-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '92e7b1c6a4d8'
down_revision: Union[str, None] = 'ec844a9fd5fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('profile_suggestion_sets', sa.Column('failure_field', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('profile_suggestion_sets', 'failure_field')