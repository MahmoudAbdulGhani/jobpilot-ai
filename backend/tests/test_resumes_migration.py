import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, User

CANDIDATE_PROFILE_REVISION = "a1b2c3d4e5f6"
REFRESH_TOKENS_REVISION = "299fe1eaa3f0"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_resume_migration_preserves_saved_data(test_engine):
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", test_engine.url.render_as_string(hide_password=False)
    )
    email = f"resume-migration-{uuid.uuid4()}@jobpilot-test.com"

    try:
        command.downgrade(config, CANDIDATE_PROFILE_REVISION)
        with Session(test_engine) as session:
            existing_user = User(email=email, password_hash="existing-auth-hash")
            session.add(existing_user)
            session.commit()
            existing_user_id = existing_user.id

        with Session(test_engine) as session:
            existing_profile = CandidateProfile(
                owner_id=existing_user_id,
                headline="Retained Senior Backend Engineer",
            )
            session.add(existing_profile)
            session.commit()

        command.upgrade(config, "head")

        inspector = inspect(test_engine)
        assert "resumes" in inspector.get_table_names()
        columns = {
            column["name"]: column for column in inspector.get_columns("resumes")
        }
        assert columns["owner_id"]["nullable"] is False
        assert columns["original_filename"]["nullable"] is False
        assert columns["display_name"]["nullable"] is False
        assert columns["file_extension"]["nullable"] is False
        assert columns["size_bytes"]["nullable"] is False
        assert columns["is_primary"]["nullable"] is False

        resume_indexes = {
            index["name"]: index for index in inspector.get_indexes("resumes")
        }
        assert "ix_resumes_owner_id" in resume_indexes
        assert resume_indexes["ix_resumes_owner_id"]["unique"] is False
        assert "uq_resumes_primary_per_owner" in resume_indexes
        assert resume_indexes["uq_resumes_primary_per_owner"]["unique"] is True
        condition = resume_indexes["uq_resumes_primary_per_owner"].get("dialect_options", {}).get("postgresql_where")
        assert "is_primary" in (condition or "")

        foreign_key = next(
            key
            for key in inspector.get_foreign_keys("resumes")
            if key["constrained_columns"] == ["owner_id"]
        )
        assert foreign_key["referred_table"] == "users"
        assert foreign_key["options"]["ondelete"] == "CASCADE"

        with Session(test_engine) as session:
            retained_user = session.scalar(select(User).where(User.id == existing_user_id))
            retained_profile = session.scalar(
                select(CandidateProfile).where(CandidateProfile.owner_id == existing_user_id)
            )
            assert retained_user is not None
            assert retained_user.email == email
            assert retained_profile is not None
            assert retained_profile.headline == "Retained Senior Backend Engineer"
            session.delete(retained_user)
            session.commit()
    finally:
        command.upgrade(config, "head")
        with Session(test_engine) as session:
            retained = session.scalar(select(User).where(User.email == email))
            if retained is not None:
                session.delete(retained)
                session.commit()


def test_resume_migration_downgrades_through_prior_heads(test_engine):
    """Downgrade straight to the pre-saved-jobs head and confirm no transient failures."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", test_engine.url.render_as_string(hide_password=False)
    )
    try:
        command.downgrade(config, REFRESH_TOKENS_REVISION)
        tables = inspect(test_engine).get_table_names()
        assert "resumes" not in tables
        assert "candidate_profiles" not in tables
        assert "saved_jobs" not in tables
        assert "refresh_tokens" in tables
    finally:
        command.upgrade(config, "head")

    inspector = inspect(test_engine)
    assert "resumes" in inspector.get_table_names()