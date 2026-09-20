"""Focused tests for the temporary production configuration diagnostic mode.

These tests verify that:
- The diagnostic flag defaults to False.
- With diagnostic=True the validator collects all failures instead of raising.
- Each failure carries a setting name and category, never a secret value.
- With diagnostic=False the validator raises on the first failure as before.
- The production entry point prints the JSON report when the env flag is set.
"""
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production(tmp_path, **overrides):
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic-ca-placeholder")
    values = dict(
        ENVIRONMENT="production",
        SECRET_KEY="aB3!cD4@eF5#gH6$iJ7%kL8^mN9&oP0*",
        POSTGRES_HOST="db.example.com",
        POSTGRES_USER="synthetic",
        POSTGRES_PASSWORD="synthetic-db-password",
        AUTH_COOKIE_SECURE=True,
        JOBPILOT_APP_URL="https://app.example.com",
        CORS_ORIGINS=["https://app.example.com"],
        ALLOWED_HOSTS=["app.example.com"],
        POSTGRES_SSLMODE="verify-full",
        POSTGRES_SSLROOTCERT=str(ca),
        JOBPILOT_STORAGE="supabase",
        JOBPILOT_STORAGE_URL="https://xyz.supabase.co",
        JOBPILOT_STORAGE_BUCKET="private-resumes",
        JOBPILOT_STORAGE_KEY="synthetic-storage-key",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


# ------------------------------------------------------------------
# 1. Default flag value
# ------------------------------------------------------------------
def test_diagnostic_flag_defaults_to_false(tmp_path):
    s = _production(tmp_path)
    assert s.JOBPILOT_CONFIG_DIAGNOSTIC is False


# ------------------------------------------------------------------
# 2. Diagnostic mode collects all failures
# ------------------------------------------------------------------
def test_diagnostic_mode_collects_all_failures(tmp_path):
    s = _production(
        tmp_path,
        JOBPILOT_CONFIG_DIAGNOSTIC=True,
        JOBPILOT_DEBUG=True,
        POSTGRES_SSLMODE="require",
        JOBPILOT_STORAGE="local",
    )
    failures = s._production_failures
    assert isinstance(failures, list)
    assert len(failures) >= 3

    categories = {f["category"] for f in failures}
    assert "forbidden_flags" in categories
    assert "database_tls" in categories
    assert "object_storage" in categories

    for f in failures:
        assert "setting" in f
        assert "category" in f
        assert isinstance(f["setting"], str)
        assert isinstance(f["category"], str)
        assert len(f["setting"]) > 0
        assert len(f["category"]) > 0


# ------------------------------------------------------------------
# 3. No secrets leak into failure messages
# ------------------------------------------------------------------
def test_failures_never_contain_secret_values(tmp_path):
    secret = "xY9#kL2$mN5@qR8!tW3&vB6^cF0*pH"
    s = _production(
        tmp_path,
        JOBPILOT_CONFIG_DIAGNOSTIC=True,
        SECRET_KEY="x" * 40,
        POSTGRES_PASSWORD=secret,
        JOBPILOT_STORAGE_KEY=secret,
    )
    all_text = json.dumps(s._production_failures)
    assert secret not in all_text
    assert "synthetic-db-password" not in all_text
    assert "synthetic-storage-key" not in all_text


# ------------------------------------------------------------------
# 4. Each check category maps to the right setting
# ------------------------------------------------------------------
def test_cookie_security_failure(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, AUTH_COOKIE_SECURE=False)
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("AUTH_COOKIE_SECURE") == "cookie_security"


def test_forbidden_flags_catches_debug(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, JOBPILOT_DEBUG=True)
    names = {f["setting"] for f in s._production_failures}
    assert "DEBUG" in names


def test_forbidden_flags_catches_test_providers(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, E2E_TEST_MODE=True)
    names = {f["setting"] for f in s._production_failures}
    assert "E2E_TEST_MODE" in names


def test_app_origin_failure(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, JOBPILOT_APP_URL="http://insecure.example.com")
    cats = {f["category"] for f in s._production_failures}
    assert "app_origin" in cats


def test_allowed_hosts_failure(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, ALLOWED_HOSTS=["localhost"])
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("ALLOWED_HOSTS") == "allowed_hosts"


def test_database_tls_failure(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, POSTGRES_SSLMODE="require")
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("POSTGRES_SSLMODE") == "database_tls"


def test_sslrootcert_missing_file(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, POSTGRES_SSLROOTCERT="/nonexistent/ca.pem")
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("POSTGRES_SSLROOTCERT") == "database_tls"


def test_secret_key_weak(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, SECRET_KEY="x" * 40)
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("SECRET_KEY") == "secret_key"


def test_object_storage_missing_key(tmp_path):
    s = _production(tmp_path, JOBPILOT_CONFIG_DIAGNOSTIC=True, JOBPILOT_STORAGE_KEY="")
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("JOBPILOT_STORAGE_KEY") == "object_storage"


def test_account_email_mismatch(tmp_path):
    s = _production(
        tmp_path,
        JOBPILOT_CONFIG_DIAGNOSTIC=True,
        JOBPILOT_ACCOUNT_MAIL_TRANSPORT="smtp",
        JOBPILOT_ACCOUNT_APP_URL="https://other.example.com",
        JOBPILOT_ACCOUNT_SMTP_HOST="smtp.example.com",
        JOBPILOT_ACCOUNT_MAIL_FROM="noreply@example.com",
    )
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("JOBPILOT_ACCOUNT_MAIL_TRANSPORT") == "account_email"


def test_mailbox_redirects_mismatch(tmp_path):
    s = _production(
        tmp_path,
        JOBPILOT_CONFIG_DIAGNOSTIC=True,
        JOBPILOT_GOOGLE_CLIENT_ID="real-client-id",
        JOBPILOT_GOOGLE_CLIENT_SECRET="real-secret",
        JOBPILOT_GOOGLE_REDIRECT_URI="https://wrong.example.com/callback",
        JOBPILOT_MAILBOX_SETTINGS_URL="https://wrong.example.com/settings",
    )
    cats = {f["setting"]: f["category"] for f in s._production_failures}
    assert cats.get("JOBPILOT_GOOGLE_REDIRECT_URI") == "mailbox_redirects"
    assert cats.get("JOBPILOT_MAILBOX_SETTINGS_URL") == "mailbox_redirects"


# ------------------------------------------------------------------
# 5. Without diagnostic flag, validator still raises on first failure
# ------------------------------------------------------------------
def test_default_mode_raises_on_first_failure(tmp_path):
    with pytest.raises(ValidationError):
        _production(tmp_path, JOBPILOT_DEBUG=True)


# ------------------------------------------------------------------
# 6. Non-production environment skips all checks
# ------------------------------------------------------------------
def test_non_production_skips_checks():
    s = Settings(
        _env_file=None,
        ENVIRONMENT="local",
        SECRET_KEY="a" * 40,
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
    )
    assert s._production_failures == []


# ------------------------------------------------------------------
# 7. Production entry point diagnostic report
# ------------------------------------------------------------------
def test_production_diagnostic_report_connectivity_fail(tmp_path, monkeypatch, capsys):
    """Diagnostic reports connectivity failure for unreachable host."""
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic-ca")
    env = {
        "ENVIRONMENT": "production",
        "JOBPILOT_CONFIG_DIAGNOSTIC": "true",
        "SECRET_KEY": "aB3!cD4@eF5#gH6$iJ7%kL8^mN9&oP0*",
        "AUTH_COOKIE_SECURE": "true",
        "JOBPILOT_APP_URL": "https://app.example.com",
        "CORS_ORIGINS": "https://app.example.com",
        "ALLOWED_HOSTS": "app.example.com",
        "POSTGRES_HOST": "db.example.com",
        "POSTGRES_USER": "synthetic",
        "POSTGRES_PASSWORD": "synthetic-db",
        "POSTGRES_SSLMODE": "disable",
        "POSTGRES_SSLROOTCERT": str(ca),
        "JOBPILOT_STORAGE": "supabase",
        "JOBPILOT_STORAGE_URL": "https://xyz.supabase.co",
        "JOBPILOT_STORAGE_BUCKET": "private-resumes",
        "JOBPILOT_STORAGE_KEY": "key",
    }
    monkeypatch.setattr(os, "environ", env)
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.production import _diagnostic_report
    with pytest.raises(SystemExit) as exc_info:
        _diagnostic_report()
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    import json
    report = json.loads(captured.out)
    assert report["status"] == "config_diagnostic"
    categories = [s["category"] for s in report["steps"]]
    assert "settings" in categories
    assert "config_validation" in categories
    assert "connectivity" in categories

    fail_steps = [s for s in report["steps"] if s["status"] == "fail"]
    assert any(s["category"] == "connectivity" for s in fail_steps)

    get_settings.cache_clear()


def test_production_diagnostic_report_silent_when_disabled(monkeypatch, capsys):
    env = {"ENVIRONMENT": "local"}
    monkeypatch.setattr(os, "environ", env)
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.production import _diagnostic_report
    _diagnostic_report()
    captured = capsys.readouterr()
    assert "config_diagnostic" not in captured.out

    get_settings.cache_clear()


def test_diagnostic_report_covers_app_import_step(tmp_path, monkeypatch, capsys):
    """Even when connectivity fails, app_import step is attempted."""
    ca = tmp_path / "ca.pem"
    ca.write_text("synthetic-ca")
    env = {
        "ENVIRONMENT": "production",
        "JOBPILOT_CONFIG_DIAGNOSTIC": "true",
        "SECRET_KEY": "aB3!cD4@eF5#gH6$iJ7%kL8^mN9&oP0*",
        "AUTH_COOKIE_SECURE": "true",
        "JOBPILOT_APP_URL": "https://app.example.com",
        "CORS_ORIGINS": "https://app.example.com",
        "ALLOWED_HOSTS": "app.example.com",
        "POSTGRES_HOST": "db.example.com",
        "POSTGRES_USER": "synthetic",
        "POSTGRES_PASSWORD": "synthetic-db",
        "POSTGRES_SSLMODE": "disable",
        "POSTGRES_SSLROOTCERT": str(ca),
        "JOBPILOT_STORAGE": "supabase",
        "JOBPILOT_STORAGE_URL": "https://xyz.supabase.co",
        "JOBPILOT_STORAGE_BUCKET": "private-resumes",
        "JOBPILOT_STORAGE_KEY": "key",
    }
    monkeypatch.setattr(os, "environ", env)
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.production import _diagnostic_report
    with pytest.raises(SystemExit):
        _diagnostic_report()

    captured = capsys.readouterr()
    import json
    report = json.loads(captured.out)
    categories = [s["category"] for s in report["steps"]]
    assert "app_import" in categories

    get_settings.cache_clear()
