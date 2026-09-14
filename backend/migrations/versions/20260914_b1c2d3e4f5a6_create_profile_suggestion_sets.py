"""create profile suggestion sets

Revision ID: b1c2d3e4f5a6
Revises: 6a7b8c9d0e1f
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "6a7b8c9d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_suggestion_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("resume_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("profile_revision", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("suggestions", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("outcome_message", sa.String(500), nullable=True),
        sa.Column("applied_selection_hash", sa.String(64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("apply_result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_id"], ["resume_extractions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_suggestion_sets_owner_id", "profile_suggestion_sets", ["owner_id"])
    op.create_index("ix_profile_suggestion_sets_resume_id", "profile_suggestion_sets", ["resume_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_suggestion_sets_resume_id", table_name="profile_suggestion_sets")
    op.drop_index("ix_profile_suggestion_sets_owner_id", table_name="profile_suggestion_sets")
    op.drop_table("profile_suggestion_sets")
