"""Production web entry point. Migrations are a separate release operation."""
import os
from app.core.config import get_settings
from app.core.operations import production_logging


def _diagnostic_report():
    """Report exception type and category for every startup step.

    Never prints secrets, connection strings, hostnames, passwords,
    SQL values or row data.  Designed to run only when
    JOBPILOT_CONFIG_DIAGNOSTIC=true so the normal path is untouched.
    """
    import json as _json
    env_diagnostic = os.environ.get("JOBPILOT_CONFIG_DIAGNOSTIC", "").lower() in ("true", "1", "yes")
    if not env_diagnostic:
        return

    steps = []

    def _ok(category):
        steps.append({"category": category, "status": "ok"})

    def _fail(category, exc):
        steps.append({"category": category, "status": "fail",
                       "error_type": type(exc).__name__})

    # 1. Settings
    try:
        from app.core.config import get_settings
        settings = get_settings()
        _ok("settings")
    except Exception as exc:
        _fail("settings", exc)
        print(_json.dumps({"status": "config_diagnostic", "steps": steps}, indent=2))
        raise SystemExit(1)

    # 2. Production config validation
    cfg_failures = getattr(settings, "_production_failures", [])
    if cfg_failures:
        steps.append({"category": "config_validation", "status": "fail",
                       "error_type": "ValidationError",
                       "failures": cfg_failures})
    else:
        _ok("config_validation")

    # 3. PORT
    try:
        port = int(os.environ.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("port out of range")
        _ok("port")
    except Exception as exc:
        _fail("port", exc)

    # 4. Engine creation (tests database URL + driver + TLS CA file)
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(
            settings.database_url, hide_parameters=True,
            pool_size=1, max_overflow=0, pool_timeout=5,
            connect_args={"connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT,
                          "sslmode": settings.POSTGRES_SSLMODE,
                          **({"sslrootcert": settings.POSTGRES_SSLROOTCERT}
                             if settings.POSTGRES_SSLROOTCERT else {})},
        )
        _ok("engine_created")
    except Exception as exc:
        _fail("engine_created", exc)
        engine = None

    # 5. Database connectivity
    if engine is not None:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            _ok("connectivity")
        except Exception as exc:
            _fail("connectivity", exc)

    # 6. App import (triggers create_application → route imports → db engine)
    try:
        import importlib
        importlib.import_module("app.main")
        _ok("app_import")
    except Exception as exc:
        _fail("app_import", exc)

    if engine is not None:
        engine.dispose()

    print(_json.dumps({"status": "config_diagnostic", "steps": steps}, indent=2))
    has_fail = any(s["status"] == "fail" for s in steps)
    raise SystemExit(1 if has_fail else 0)


def main():
    production_logging()
    _diagnostic_report()
    try:
        settings = get_settings()
        if settings.ENVIRONMENT != 'production': raise ValueError()
        port = int(os.environ.get('PORT', '8000'))
        if not 1 <= port <= 65535: raise ValueError()
    except Exception:
        raise SystemExit('Production configuration invalid; consult the deployment runbook') from None
    import uvicorn
    uvicorn.run('app.main:app', host='0.0.0.0', port=port, workers=1,
                access_log=False, log_config=None,
                proxy_headers=bool(settings.JOBPILOT_PROXY_IPS),
                forwarded_allow_ips=settings.JOBPILOT_PROXY_IPS)


if __name__ == '__main__': main()
