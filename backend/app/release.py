"""Explicit, serialized release migration. Never invoked by a web worker."""
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.core.db import engine


def main():
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '30s'"))
            connection.execute(text('SELECT pg_advisory_xact_lock(52473261019)'))
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
    except Exception:
        raise SystemExit('Release migration failed; inspect schema state securely before retrying') from None


if __name__ == '__main__': main()
