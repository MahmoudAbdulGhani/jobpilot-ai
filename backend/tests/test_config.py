import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def make_settings(monkeypatch: pytest.MonkeyPatch, **overrides) -> Settings:
    required = {
        "SECRET_KEY": "x" * 48,
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
    }
    for key, value in required.items():
        monkeypatch.setenv(key, value)
    for key, value in overrides.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, str(value))
    return Settings(_env_file=None)


def test_defaults_are_applied(monkeypatch: pytest.MonkeyPatch):
    settings = make_settings(
        monkeypatch,
        APP_NAME=None,
        ENVIRONMENT=None,
        JOBPILOT_DEBUG=None,
        API_PREFIX=None,
        CORS_ORIGINS=None,
    )

    assert settings.APP_NAME == "JobPilot AI"
    assert settings.ENVIRONMENT == "local"
    assert settings.DEBUG is False
    assert settings.API_PREFIX == "/api"
    assert settings.CORS_ORIGINS == ["http://localhost:3000"]


def test_missing_secret_key_fails_validation(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValidationError) as error:
        make_settings(monkeypatch, SECRET_KEY=None)

    assert "SECRET_KEY" in str(error.value)


def test_short_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValidationError) as error:
        make_settings(monkeypatch, SECRET_KEY="too-short")

    assert "at least 32 characters" in str(error.value)


def test_cors_origins_split_from_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = make_settings(
        monkeypatch,
        CORS_ORIGINS="http://localhost:3000, http://127.0.0.1:3000 ,",
    )

    assert settings.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_invalid_environment_value_is_rejected(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValidationError) as error:
        make_settings(monkeypatch, ENVIRONMENT="staging")

    assert "ENVIRONMENT" in str(error.value)


def test_jobpilot_debug_string_is_coerced_to_bool(monkeypatch: pytest.MonkeyPatch):
    assert make_settings(monkeypatch, JOBPILOT_DEBUG="true").DEBUG is True
    assert make_settings(monkeypatch, JOBPILOT_DEBUG="false").DEBUG is False


def test_unrelated_debug_environment_variable_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DEBUG", "release")

    assert make_settings(monkeypatch, JOBPILOT_DEBUG="false").DEBUG is False


def test_get_settings_returns_cached_instance():
    assert get_settings() is get_settings()
