"""Production web entry point. Migrations are a separate release operation."""
import os
from app.core.config import get_settings
from app.core.operations import production_logging


def main():
    production_logging()
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
