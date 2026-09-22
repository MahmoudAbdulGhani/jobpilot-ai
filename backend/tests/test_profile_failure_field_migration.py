import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

PRIOR_HEAD = "ec844a9fd5fb"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
pytestmark = pytest.mark.destructive_database


def _seed_record(engine, email):
    now = datetime.now(timezone.utc).isoformat()
    user_id = uuid.uuid4()
    resume_id = uuid.uuid4()
    extraction_id = uuid.uuid4()
    record_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at)"
                " VALUES (:id, :email, 'existing-auth-hash', TRUE, :ts, :ts)"
            ),
            {"id": user_id, "email": email, "ts": now},
        )
        connection.execute(
            text(
                "INSERT INTO resumes (id, owner_id, original_filename, display_name,"
                " file_extension, size_bytes, is_primary, created_at, updated_at)"
                " VALUES (:id, :owner_id, 'cv.pdf', 'cv.pdf', 'pdf', 1024, FALSE, :ts, :ts)"
            ),
            {"id": resume_id, "owner_id": user_id, "ts": now},
        )
        connection.execute(
            text(
                "INSERT INTO resume_extractions (id, resume_id, status, reviewed_at,"
                " created_at, updated_at)"
                " VALUES (:id, :resume_id, 'succeeded', :ts, :ts, :ts)"
            ),
            {"id": extraction_id, "resume_id": resume_id, "ts": now},
        )
        connection.execute(
            text(
                "INSERT INTO profile_suggestion_sets"
                " (id, owner_id, resume_id, extraction_id, source_text, source_hash,"
                "  source_reviewed_at, profile_revision, status, suggestions, provider,"
                "  model, prompt_version, outcome_message, created_at, updated_at)"
                " VALUES (:id, :owner_id, :resume_id, :extraction_id, 'Synthetic source',"
                "  :source_hash, :ts, 'none', 'failed', NULL, 'openai', 'gpt-5-mini',"
                "  'profile-suggestions-v3', 'invalid_field_value', :ts, :ts)"
            ),
            {
                "id": record_id, "owner_id": user_id, "resume_id": resume_id,
                "extraction_id": extraction_id, "source_hash": "a" * 64, "ts": now,
            },
        )
    return user_id, record_id


def test_failure_field_migration_is_additive_and_preserves_rows(disposable_engine):
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", disposable_engine.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    email = f"failure-field-migrate-{uuid.uuid4()}@jobpilot-test.com"

    def columns():
        return inspect(disposable_engine).get_columns("profile_suggestion_sets")

    user_id, record_id = _seed_record(disposable_engine, email)

    try:
        head_columns = {column["name"]: column for column in columns()}
        assert head_columns["failure_field"]["nullable"] is True
        with disposable_engine.connect() as connection:
            row = connection.execute(
                text("SELECT outcome_message, failure_field FROM profile_suggestion_sets WHERE id = :id"),
                {"id": record_id},
            ).one()
        assert row.outcome_message == "invalid_field_value"
        assert row.failure_field is None

        with disposable_engine.begin() as connection:
            connection.execute(
                text("UPDATE profile_suggestion_sets SET failure_field = 'experience' WHERE id = :id"),
                {"id": record_id},
            )
        with disposable_engine.connect() as connection:
            value = connection.execute(
                text("SELECT failure_field FROM profile_suggestion_sets WHERE id = :id"),
                {"id": record_id},
            ).scalar_one()
        assert value == "experience"

        command.downgrade(config, PRIOR_HEAD)
        prior_columns = {column["name"] for column in columns()}
        assert "failure_field" not in prior_columns
        with disposable_engine.connect() as connection:
            outcome = connection.execute(
                text("SELECT outcome_message FROM profile_suggestion_sets WHERE id = :id"),
                {"id": record_id},
            ).scalar_one()
        assert outcome == "invalid_field_value"

        command.upgrade(config, "head")
        restored_columns = {column["name"]: column for column in columns()}
        assert restored_columns["failure_field"]["nullable"] is True
        with disposable_engine.connect() as connection:
            outcome, field = connection.execute(
                text(
                    "SELECT outcome_message, failure_field FROM profile_suggestion_sets WHERE id = :id"
                ),
                {"id": record_id},
            ).one()
        assert outcome == "invalid_field_value"
        assert field is None
    finally:
        command.upgrade(config, "head")
        with disposable_engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})