import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, get_settings
from app.core.db import assert_is_test_database
from app.models import User


def test_dev_and_test_databases_are_separate():
    settings = get_settings()

    assert settings.database_url != settings.test_database_url
    assert settings.database_url.endswith(f"/{settings.POSTGRES_DB}")
    assert settings.test_database_url.endswith(f"/{settings.POSTGRES_TEST_DB}")


def test_masked_url_hides_password():
    settings = get_settings()

    masked = settings.database_url_masked

    assert ":***@" in masked
    assert settings.POSTGRES_PASSWORD not in masked


def test_missing_postgres_password_fails_validation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "POSTGRES_PASSWORD" in str(error.value)


def test_safety_guard_allows_test_database():
    settings = get_settings()

    assert_is_test_database(settings.test_database_url, settings.POSTGRES_TEST_DB)


def test_safety_guard_rejects_development_database():
    settings = get_settings()

    with pytest.raises(RuntimeError) as error:
        assert_is_test_database(settings.database_url, settings.POSTGRES_TEST_DB)

    assert "Safety stop" in str(error.value)


def test_migrations_created_users_table(test_engine):
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()

    assert "users" in tables
    assert "alembic_version" in tables

    columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"id", "email", "password_hash", "is_active", "created_at", "updated_at"} <= columns


def test_user_roundtrip(db_session):
    user = User(email=f"{uuid.uuid4()}@example.com", password_hash="hashed-secret")

    db_session.add(user)
    db_session.commit()

    found = db_session.scalar(select(User).where(User.email == user.email))

    assert found is not None
    assert found.id == user.id
    assert found.is_active is True
    assert found.created_at is not None
    assert found.updated_at is not None


def test_duplicate_email_is_rejected(db_session):
    email = f"{uuid.uuid4()}@example.com"
    db_session.add(User(email=email, password_hash="first"))
    db_session.commit()
    db_session.add(User(email=email, password_hash="second"))

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
