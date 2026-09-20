"""Read-only release diagnostic for Render Shell.

Reports only category and exception type.  Never prints secrets,
connection strings, hostnames, passwords, SQL values or row data.

Command to run once from Render Shell:
    cd /app/backend && python -m app.release_diag
"""
import json
import time


def _report(entry):
    print(json.dumps(entry, indent=2))


def run():
    print("=" * 60)
    print("Release diagnostic (read-only)")
    print("=" * 60)

    # 1. Load settings
    try:
        from app.core.config import get_settings
        settings = get_settings()
        _report({"category": "settings", "status": "ok"})
    except Exception as exc:
        _report({"category": "settings", "status": "fail",
                 "error_type": type(exc).__name__})
        print("=" * 60)
        return

    # 2. Build engine (validates URL construction + driver import)
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(
            settings.database_url,
            hide_parameters=True,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            pool_timeout=5,
            connect_args={
                "connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT,
                "sslmode": settings.POSTGRES_SSLMODE,
                **({"sslrootcert": settings.POSTGRES_SSLROOTCERT}
                   if settings.POSTGRES_SSLROOTCERT else {}),
            },
        )
        _report({"category": "engine_created", "status": "ok"})
    except Exception as exc:
        _report({"category": "engine_created", "status": "fail",
                 "error_type": type(exc).__name__})
        print("=" * 60)
        return

    # 3. Test connectivity (TLS, auth, network)
    t0 = time.monotonic()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - t0) * 1000)
        _report({"category": "connectivity", "status": "ok",
                 "latency_ms": latency_ms})
    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000)
        detail = str(exc).lower()
        if "password authentication failed" in detail:
            sub = "auth_failed"
        elif "does not exist" in detail and "role" in detail:
            sub = "role_missing"
        elif "ssl" in detail or "certificate" in detail:
            sub = "tls_error"
        elif "timeout" in detail or "timed out" in detail:
            sub = "connect_timeout"
        elif "connection refused" in detail:
            sub = "connection_refused"
        elif "could not translate host name" in detail:
            sub = "dns_resolution_failed"
        else:
            sub = "unknown"
        _report({"category": "connectivity", "status": "fail",
                 "error_type": type(exc).__name__, "subcategory": sub,
                 "latency_ms": latency_ms})
        engine.dispose()
        print("=" * 60)
        return

    # 4. Check alembic_version table (read-only, no upgrade)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                     "WHERE table_name = 'alembic_version')")
            )
            table_exists = result.scalar()
        if not table_exists:
            _report({"category": "alembic_version", "status": "empty_database",
                     "detail": "alembic_version table does not exist"})
        else:
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                )
                rows = result.fetchall()
            if not rows:
                _report({"category": "alembic_version", "status": "empty",
                         "detail": "alembic_version table exists but has no rows"})
            elif len(rows) == 1:
                rev = rows[0][0]
                _report({"category": "alembic_version", "status": "current",
                         "revision": rev})
            else:
                revisions = [r[0] for r in rows]
                _report({"category": "alembic_version", "status": "multiple_heads",
                         "detail": f"{len(revisions)} rows found"})
    except Exception as exc:
        _report({"category": "alembic_version", "status": "fail",
                 "error_type": type(exc).__name__})

    # 5. Check alembic head matches code (read-only comparison)
    try:
        from pathlib import Path
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config(
            str(Path(__file__).resolve().parents[1] / "alembic.ini")
        )
        config.set_main_option(
            "script_location",
            str(Path(__file__).resolve().parents[1] / "migrations"),
        )
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        _report({"category": "alembic_code_heads", "status": "ok",
                 "heads": heads})
    except Exception as exc:
        _report({"category": "alembic_code_heads", "status": "fail",
                 "error_type": type(exc).__name__})

    # 6. Advisory lock test (same lock as app.release, read-only try)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT pg_try_advisory_lock(52473261019)")
            )
            locked = result.scalar()
        if locked:
            _report({"category": "advisory_lock", "status": "ok",
                     "detail": "lock acquired (not held by release process)"})
            with engine.connect() as conn:
                conn.execute(text("SELECT pg_advisory_unlock(52473261019)"))
        else:
            _report({"category": "advisory_lock", "status": "busy",
                     "detail": "lock held by another session (release may be running)"})
    except Exception as exc:
        _report({"category": "advisory_lock", "status": "fail",
                 "error_type": type(exc).__name__})

    engine.dispose()
    print("=" * 60)
    print("Diagnostic complete.")


if __name__ == "__main__":
    run()