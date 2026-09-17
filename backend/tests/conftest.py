import os

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-with-at-least-32-chars!")

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from database_safety import disposable_url, require_disposable_target, guard_sql, UnsafeTestDatabase
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import assert_is_test_database
from app.main import create_application

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def pytest_configure(config):
    config.addinivalue_line("markers", "destructive_database: requires a separately authorized disposable database")


def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("destructive_database"):
            if os.environ.get("JOBPILOT_ALLOW_DESTRUCTIVE_TESTS") != "1":
                item.add_marker(pytest.mark.skip(reason="Disposable database not authorized; destructive coverage not run"))
            else:
                try:
                    disposable_url(get_settings(), os.environ)
                except UnsafeTestDatabase as error:
                    raise pytest.UsageError(str(error)) from None


@pytest.fixture(scope="session", autouse=True)
def protect_database_operations():
    # Runtime guards still apply if a marker is omitted or a target is changed.
    original = command.downgrade
    def guarded_downgrade(config, *args, **kwargs):
        require_disposable_target(config.get_main_option("sqlalchemy.url"), get_settings(), os.environ)
        return original(config, *args, **kwargs)
    def before_execute(connection, cursor, statement, parameters, context, executemany):
        guard_sql(connection.engine.url, statement, get_settings(), os.environ)
    command.downgrade = guarded_downgrade
    event.listen(Engine, "before_cursor_execute", before_execute)
    try:
        yield
    finally:
        event.remove(Engine, "before_cursor_execute", before_execute)
        command.downgrade = original


@pytest.fixture(scope="session")
def disposable_engine():
    settings = get_settings()
    try:
        target = disposable_url(settings, os.environ)
    except UnsafeTestDatabase as error:
        pytest.fail(str(error))
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", target.render_as_string(hide_password=False).replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_engine(target, connect_args={"connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT})
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_application())


@pytest.fixture(scope="session")
def test_engine():
    settings = get_settings()
    assert_is_test_database(settings.test_database_url, settings.POSTGRES_TEST_DB)

    # Persistent browser/test database: no implicit migrations or truncation.
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
