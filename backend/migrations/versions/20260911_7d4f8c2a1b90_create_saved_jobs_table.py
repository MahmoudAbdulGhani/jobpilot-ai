"""create saved jobs table

Revision ID: 7d4f8c2a1b90
Revises: 299fe1eaa3f0
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7d4f8c2a1b90"
down_revision: Union[str, None] = "299fe1eaa3f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_archived", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
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
            name=op.f("fk_saved_jobs_users_owner_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_jobs")),
    )
    op.create_index(
        op.f("ix_saved_jobs_owner_id"), "saved_jobs", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_saved_jobs_owner_archived_created_id",
        "saved_jobs",
        ["owner_id", "is_archived", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_saved_jobs_owner_archived_created_id", table_name="saved_jobs"
    )
    op.drop_index(op.f("ix_saved_jobs_owner_id"), table_name="saved_jobs")
    op.drop_table("saved_jobs")
