"""create candidate profiles table

Revision ID: a1b2c3d4e5f6
Revises: 7d4f8c2a1b90
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "7d4f8c2a1b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("headline", sa.String(length=200), nullable=True),
        sa.Column("target_roles", sa.JSON(), nullable=True),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("remote_preference", sa.String(length=20), nullable=True),
        sa.Column("work_authorization", sa.String(length=40), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("experience", sa.JSON(), nullable=True),
        sa.Column("education", sa.JSON(), nullable=True),
        sa.Column("languages", sa.JSON(), nullable=True),
        sa.Column("salary_preference", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_candidate_profiles_users_owner_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_profiles")),
    )
    op.create_index(
        op.f("ix_candidate_profiles_owner_id"),
        "candidate_profiles",
        ["owner_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_candidate_profiles_owner_id"), table_name="candidate_profiles"
    )
    op.drop_table("candidate_profiles")