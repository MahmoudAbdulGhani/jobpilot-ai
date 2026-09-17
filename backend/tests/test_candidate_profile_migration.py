import uuid
from pathlib import Path

import pytest

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import SavedJob, User

SAVED_JOBS_REVISION = "7d4f8c2a1b90"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
pytestmark = pytest.mark.destructive_database


def test_candidate_profile_migration_preserves_saved_data(disposable_engine):
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", disposable_engine.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    email = f"profile-migration-{uuid.uuid4()}@jobpilot-test.com"

    try:
        command.downgrade(config, SAVED_JOBS_REVISION)
        with Session(disposable_engine) as session:
            existing_user = User(email=email, password_hash="existing-auth-hash")
            session.add(existing_user)
            session.commit()
            existing_user_id = existing_user.id

        with Session(disposable_engine) as session:
            existing_job = SavedJob(
                owner_id=existing_user_id,
                title="Preserved Role",
                company="Retention Co",
            )
            session.add(existing_job)
            session.commit()
            existing_job_id = existing_job.id

        command.upgrade(config, "head")

        inspector = inspect(disposable_engine)
        assert "candidate_profiles" in inspector.get_table_names()
        columns = {
            column["name"]: column
            for column in inspector.get_columns("candidate_profiles")
        }
        assert columns["owner_id"]["nullable"] is False
        profile_indexes = {
            index["name"]: index for index in inspector.get_indexes("candidate_profiles")
        }
        assert "ix_candidate_profiles_owner_id" in profile_indexes
        assert profile_indexes["ix_candidate_profiles_owner_id"]["unique"] is True
        foreign_key = next(
            key
            for key in inspector.get_foreign_keys("candidate_profiles")
            if key["constrained_columns"] == ["owner_id"]
        )
        assert foreign_key["referred_table"] == "users"
        assert foreign_key["options"]["ondelete"] == "CASCADE"
        with Session(disposable_engine) as session:
            retained_user = session.scalar(select(User).where(User.id == existing_user_id))
            retained_job = session.scalar(
                select(SavedJob).where(SavedJob.id == existing_job_id)
            )
            assert retained_user is not None
            assert retained_user.email == email
            assert retained_job is not None
            assert retained_job.title == "Preserved Role"
            session.delete(retained_user)
            session.commit()
    finally:
        command.upgrade(config, "head")
        with Session(disposable_engine) as session:
            retained = session.scalar(select(User).where(User.email == email))
            if retained is not None:
                session.delete(retained)
                session.commit()