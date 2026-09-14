"""Application packs, immutable document versions and content-free AI quota.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
"""
from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False) for name in ("created_at", "updated_at")]


def upgrade():
    op.create_table(
        "application_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *[sa.Column(name, sa.Uuid(), sa.ForeignKey(f"{table}.id", ondelete="CASCADE"), nullable=False) for name, table in (
            ("owner_id", "users"), ("job_id", "saved_jobs"), ("profile_id", "candidate_profiles"),
            ("resume_id", "resumes"), ("extraction_id", "resume_extractions"),
        )],
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("generated", sa.JSON(), nullable=True),
        sa.Column("review_notes", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("outcome_message", sa.String(500), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        *timestamps(), sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_pack_owner_key"),
    )
    op.create_index("ix_application_packs_owner_id", "application_packs", ["owner_id"])
    op.create_index("ix_application_packs_job_id", "application_packs", ["job_id"])
    op.create_index("uq_pack_owner_generating", "application_packs", ["owner_id"], unique=True, postgresql_where=sa.text("status = 'generating'"))
    op.create_table(
        "application_pack_versions", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey("application_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("cv", sa.JSON(), nullable=False), sa.Column("cover_letter", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), *timestamps(),
        sa.UniqueConstraint("pack_id", "number", name="uq_pack_version_number"),
    )
    op.create_index("ix_application_pack_versions_pack_id", "application_pack_versions", ["pack_id"])
    op.create_table(
        "application_pack_operations", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pack_id", sa.Uuid(), sa.ForeignKey("application_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.UniqueConstraint("pack_id", "key", name="uq_pack_operation_key"),
    )
    op.create_index("ix_application_pack_operations_pack_id", "application_pack_operations", ["pack_id"])
    op.create_table(
        "ai_usage", sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("active_token", sa.Uuid(), nullable=True),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("ai_usage")
    op.drop_table("application_pack_operations")
    op.drop_table("application_pack_versions")
    op.drop_table("application_packs")
