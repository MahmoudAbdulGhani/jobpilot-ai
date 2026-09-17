import os

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-with-at-least-32-chars!")

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import assert_is_test_database
from app.main import create_application

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def pytest_collection_modifyitems(items):
    """Preservation mode must also exclude legacy schema downgrade regressions."""
    if os.environ.get("JOBPILOT_TEST_PRESERVE_DB") == "1":
        for item in items:
            if "command.downgrade(" in Path(item.path).read_text(encoding="utf-8"):
                item.add_marker(pytest.mark.skip(reason="Schema downgrade is forbidden in database preservation mode"))


def _truncate_all_tables(database_url: str) -> None:
    """Empty every table so each test session starts from a known state.

    The connected browser suites share the same guarded test database and may
    leave disposable users, jobs, and resumes behind, so pytest must not rely
    on a pre-existing empty database.
    """
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    """
                    DO $$
                    DECLARE row RECORD;
                    BEGIN
                        FOR row IN
                            SELECT tablename
                            FROM pg_tables
                            WHERE schemaname = 'public'
                              AND tablename <> 'alembic_version'
                        LOOP
                            EXECUTE format(
                                'TRUNCATE TABLE public.%I RESTART IDENTITY CASCADE',
                                row.tablename
                            );
                        END LOOP;
                    END $$;
                    """
                )
            )
            connection.commit()
    finally:
        engine.dispose()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_application())


@pytest.fixture(scope="session")
def test_engine():
    settings = get_settings()
    assert_is_test_database(settings.test_database_url, settings.POSTGRES_TEST_DB)

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", settings.test_database_url)
    command.upgrade(config, "head")
    if os.environ.get("JOBPILOT_TEST_PRESERVE_DB") != "1":
        _truncate_all_tables(settings.test_database_url)

    return create_engine(
        settings.test_database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT},
    )


@pytest.fixture()
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
