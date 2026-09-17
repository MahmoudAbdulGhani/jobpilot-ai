"""Safety checks use fake URLs and blocked connections; never execute migrations."""
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from database_safety import (UnsafeTestDatabase, disposable_url,
    require_disposable_target, guard_sql)

SETTINGS = SimpleNamespace(POSTGRES_DB="private_dev", POSTGRES_TEST_DB="persistent_browser")
URL = "postgresql+psycopg://test:never-log-this@localhost/jobpilot_disposable_unit"


def opt_in(**overrides):
    return {"JOBPILOT_ALLOW_DESTRUCTIVE_TESTS":"1", "JOBPILOT_DISPOSABLE_DATABASE_URL":URL,
        "JOBPILOT_DISPOSABLE_DATABASE_CONFIRM":"jobpilot_disposable_unit", **overrides}


@pytest.fixture(autouse=True)
def no_connections(monkeypatch):
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: pytest.fail("No database connection allowed"))


def test_explicit_disposable_authorization_is_pure():
    assert disposable_url(SETTINGS, opt_in()) == make_url(URL)
    require_disposable_target(URL, SETTINGS, opt_in())
    guard_sql(URL, "TRUNCATE TABLE fake", SETTINGS, opt_in())  # Check only; never execute SQL.


@pytest.mark.parametrize("env", [{}, opt_in(JOBPILOT_ALLOW_DESTRUCTIVE_TESTS="0"),
    opt_in(JOBPILOT_DISPOSABLE_DATABASE_CONFIRM="wrong"), opt_in(JOBPILOT_TEST_PRESERVE_DB="1"),
    opt_in(JOBPILOT_DISPOSABLE_DATABASE_URL="invalid-secret-url"),
    opt_in(JOBPILOT_DISPOSABLE_DATABASE_URL=URL+"?options=unsafe")])
def test_missing_or_invalid_authorization_fails_closed(env):
    with pytest.raises(UnsafeTestDatabase) as caught: disposable_url(SETTINGS, env)
    assert "never-log-this" not in str(caught.value) and "invalid-secret-url" not in str(caught.value)


@pytest.mark.parametrize("name", ["jobpilot", "jobpilot_test", "private_dev", "persistent_browser", "postgres", "template1", "unconfirmed"])
def test_persistent_and_system_databases_are_rejected_even_with_confirmation(name):
    with pytest.raises(UnsafeTestDatabase):
        disposable_url(SETTINGS, opt_in(JOBPILOT_DISPOSABLE_DATABASE_URL=f"postgresql+psycopg://x@elsewhere/{name}", JOBPILOT_DISPOSABLE_DATABASE_CONFIRM=name))


def test_configured_persistent_database_with_disposable_name_is_rejected():
    settings = SimpleNamespace(POSTGRES_DB="jobpilot_disposable_unit", POSTGRES_TEST_DB="browser")
    with pytest.raises(UnsafeTestDatabase): disposable_url(settings, opt_in())


@pytest.mark.parametrize("sql", ["DROP TABLE jobs", "TRUNCATE jobs", "DO $$ BEGIN EXECUTE 'TRUNCATE jobs'; END $$"])
def test_runtime_sql_target_cannot_switch_to_persistent_database(sql):
    with pytest.raises(UnsafeTestDatabase): guard_sql("postgresql+psycopg://x@localhost/jobpilot_test", sql, SETTINGS, opt_in())


def test_read_only_sql_needs_no_destructive_authorization():
    guard_sql("postgresql+psycopg://x@localhost/jobpilot_test", "SELECT 1", SETTINGS, {})


def test_actual_alembic_downgrade_is_blocked_before_connecting(monkeypatch):
    monkeypatch.delenv("JOBPILOT_ALLOW_DESTRUCTIVE_TESTS", raising=False)
    config = Config()
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://x@localhost/jobpilot_test")
    with pytest.raises(UnsafeTestDatabase): command.downgrade(config, "base")


def test_actual_sqlalchemy_listener_blocks_reset_before_execution(monkeypatch):
    from sqlalchemy import create_engine
    monkeypatch.delenv("JOBPILOT_ALLOW_DESTRUCTIVE_TESTS", raising=False)
    engine = create_engine("postgresql+psycopg://x@localhost/jobpilot_test")
    try:
        with pytest.raises(UnsafeTestDatabase):
            engine.dispatch.before_cursor_execute(SimpleNamespace(engine=engine), None,
                "TRUNCATE saved_jobs", None, None, False)
    finally:
        engine.dispose()


def test_persistent_fixture_never_migrates_or_resets(monkeypatch):
    import conftest
    monkeypatch.setattr(conftest.command, "upgrade", lambda *a, **k: pytest.fail("Unexpected migration"))
    sentinel = object()
    monkeypatch.setattr(conftest, "create_engine", lambda *a, **k: sentinel)
    assert conftest.test_engine.__wrapped__() is sentinel


def test_invalid_explicit_opt_in_aborts_collection(monkeypatch):
    import conftest
    monkeypatch.setenv("JOBPILOT_ALLOW_DESTRUCTIVE_TESTS", "1")
    monkeypatch.setenv("JOBPILOT_DISPOSABLE_DATABASE_URL", "not-a-valid-url")
    item = SimpleNamespace(get_closest_marker=lambda name: True)
    with pytest.raises(pytest.UsageError): conftest.pytest_collection_modifyitems([item])
