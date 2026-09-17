import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def read_database_health() -> dict[str, str]:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )
    return {"status": "ok", "database": "reachable"}


@router.get("/ready")
def readiness():
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    try:
        config = Config(str(Path(__file__).resolve().parents[3] / 'alembic.ini'))
        config.set_main_option('script_location', str(Path(__file__).resolve().parents[3] / 'migrations'))
        expected = ScriptDirectory.from_config(config).get_current_head()
        with SessionLocal() as session:
            session.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            actual = session.scalar(text('SELECT version_num FROM alembic_version'))
            if actual != expected: raise RuntimeError()
    except Exception:
        raise HTTPException(503, 'Application is not ready') from None
    # Optional providers are never contacted by platform health probes.
    return {'status':'ready','database':'reachable','schema':'current'}
