import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.api.routes import health as health_module
from app.core.config import Settings

FORBIDDEN_SNIPPETS = ["127.0.0.1", "5433", "psycopg", "postgresql+", "Traceback"]


class _QueryFails:
    def __enter__(self) -> "_QueryFails":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def execute(self, *args, **kwargs) -> None:
        raise OperationalError("SELECT 1", {}, Exception("simulated query failure"))


class _ConnectFails:
    def __enter__(self) -> None:
        raise OperationalError("CONNECT", {}, Exception("simulated connection failure"))

    def __exit__(self, *args) -> bool:
        return False


def _use_session_factory(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    monkeypatch.setattr(health_module, "SessionLocal", factory)


def _assert_sanitized(response) -> None:
    assert response.json() == {"detail": "Database is unavailable"}
    for snippet in FORBIDDEN_SNIPPETS:
        assert snippet not in response.text


def test_health_db_returns_ok_when_database_reachable(
    client: TestClient,
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    _use_session_factory(monkeypatch, lambda: Session(bind=test_engine))

    response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}


def test_health_db_returns_sanitized_503_when_query_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _use_session_factory(monkeypatch, lambda: _QueryFails())

    response = client.get("/api/health/db")

    assert response.status_code == 503
    _assert_sanitized(response)


def test_health_db_returns_sanitized_503_when_connection_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _use_session_factory(monkeypatch, lambda: _ConnectFails())

    response = client.get("/api/health/db")

    assert response.status_code == 503
    _assert_sanitized(response)


def test_liveness_does_not_require_database(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _use_session_factory(monkeypatch, lambda: _ConnectFails())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_postgres_connect_timeout_validation(monkeypatch: pytest.MonkeyPatch):
    required = {
        "SECRET_KEY": "x" * 48,
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
    }
    for key, value in required.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)
    assert settings.POSTGRES_CONNECT_TIMEOUT == 3

    monkeypatch.setenv("POSTGRES_CONNECT_TIMEOUT", "0")
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert "positive" in str(error.value)
