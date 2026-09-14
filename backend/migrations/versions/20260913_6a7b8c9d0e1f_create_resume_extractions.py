"""create resume extractions table

Revision ID: 6a7b8c9d0e1f
Revises: 3d5e7f9b1c2d
Create Date: 2026-09-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6a7b8c9d0e1f"
down_revision: Union[str, None] = "3d5e7f9b1c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("parser_name", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], name=op.f("fk_resume_extractions_resumes_resume_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_extractions")),
        sa.UniqueConstraint("resume_id", name=op.f("uq_resume_extractions_resume_id")),
    )
    op.create_index(op.f("ix_resume_extractions_resume_id"), "resume_extractions", ["resume_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_resume_extractions_resume_id"), table_name="resume_extractions")
    op.drop_table("resume_extractions")
