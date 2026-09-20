"""Production web entry point. Migrations are a separate release operation."""
import os
from app.core.config import get_settings
from app.core.operations import production_logging


def _diagnostic_report():
    """Print every failing setting name and category.  Never prints values."""
    import json as _json
    env_diagnostic = os.environ.get("JOBPILOT_CONFIG_DIAGNOSTIC", "").lower() in ("true", "1", "yes")
    failures: list[dict] = []
    if env_diagnostic:
        try:
            settings = get_settings()
            failures = getattr(settings, "_production_failures", [])
        except Exception as exc:
            failures = [{"setting": "_init", "category": "startup", "message": str(exc)}]
    if failures:
        print(_json.dumps({"status": "config_diagnostic", "failures": failures}, indent=2))
        raise SystemExit(1)


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
