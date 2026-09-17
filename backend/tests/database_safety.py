"""Pure authorization checks: never connect, create, migrate or reset a database."""
import re

from sqlalchemy.engine import make_url


class UnsafeTestDatabase(RuntimeError):
    pass


def disposable_url(settings, environ):
    if environ.get("JOBPILOT_ALLOW_DESTRUCTIVE_TESTS") != "1":
        raise UnsafeTestDatabase("Destructive tests require explicit disposable-database opt-in.")
    if environ.get("JOBPILOT_TEST_PRESERVE_DB") == "1":
        raise UnsafeTestDatabase("Preservation mode forbids destructive tests.")
    try:
        url = make_url(environ.get("JOBPILOT_DISPOSABLE_DATABASE_URL", ""))
    except Exception:
        raise UnsafeTestDatabase("A valid disposable PostgreSQL URL is required.") from None
    name = url.database or ""
    protected = {"jobpilot", "jobpilot_test", settings.POSTGRES_DB, settings.POSTGRES_TEST_DB}
    if (url.drivername != "postgresql+psycopg" or not url.host or url.query
            or name in protected or not re.fullmatch(r"jobpilot_disposable_[a-z0-9_]+", name)
            or environ.get("JOBPILOT_DISPOSABLE_DATABASE_CONFIRM") != name):
        raise UnsafeTestDatabase("Target must be an explicitly confirmed, separate disposable database.")
    return url


def require_disposable_target(target, settings, environ):
    authorized = disposable_url(settings, environ)
    try:
        matches = make_url(target) == authorized
    except Exception:
        matches = False
    if not matches:
        raise UnsafeTestDatabase("Destructive operation target differs from the authorized disposable database.")


def guard_sql(target, statement, settings, environ):
    # Also catches reset SQL inside DO blocks, not just top-level statements.
    if re.search(r"\b(?:DROP|TRUNCATE)\b", statement, re.IGNORECASE):
        require_disposable_target(target, settings, environ)
