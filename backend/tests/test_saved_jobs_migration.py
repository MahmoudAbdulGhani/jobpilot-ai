import uuid
from pathlib import Path

import pytest

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import User

AUTH_SCHEMA_REVISION = "299fe1eaa3f0"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
pytestmark = pytest.mark.destructive_database


def test_saved_jobs_migration_preserves_existing_authentication_record(disposable_engine):
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", disposable_engine.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    email = f"migration-{uuid.uuid4()}@jobpilot-test.com"

    try:
        command.downgrade(config, AUTH_SCHEMA_REVISION)
        with Session(disposable_engine) as session:
            existing = User(email=email, password_hash="existing-authentication-hash")
            session.add(existing)
            session.commit()
            existing_id = existing.id

        command.upgrade(config, "head")

        inspector = inspect(disposable_engine)
        assert "saved_jobs" in inspector.get_table_names()
        columns = {column["name"]: column for column in inspector.get_columns("saved_jobs")}
        assert columns["owner_id"]["nullable"] is False
        assert {
            "ix_saved_jobs_owner_id",
            "ix_saved_jobs_owner_archived_created_id",
        } <= {index["name"] for index in inspector.get_indexes("saved_jobs")}
        foreign_key = next(
            key
            for key in inspector.get_foreign_keys("saved_jobs")
            if key["constrained_columns"] == ["owner_id"]
        )
        assert foreign_key["referred_table"] == "users"
        assert foreign_key["options"]["ondelete"] == "CASCADE"
        with Session(disposable_engine) as session:
            retained = session.scalar(select(User).where(User.id == existing_id))
            assert retained is not None
            assert retained.email == email
            session.delete(retained)
            session.commit()
    finally:
        command.upgrade(config, "head")
        with Session(disposable_engine) as session:
            retained = session.scalar(select(User).where(User.email == email))
            if retained is not None:
                session.delete(retained)
                session.commit()
