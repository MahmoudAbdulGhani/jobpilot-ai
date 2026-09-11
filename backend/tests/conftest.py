import os

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-with-at-least-32-chars!")

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import assert_is_test_database
from app.main import create_application

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


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
