from collections.abc import Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def assert_is_test_database(url: str, expected_test_db: str) -> None:
    target = urlparse(url).path.lstrip("/")
    if target != expected_test_db:
        raise RuntimeError(
            f"Safety stop: tests may only use the '{expected_test_db}' database, "
            f"not '{target}'"
        )


settings = get_settings()

engine = create_engine(
    settings.database_url,
    hide_parameters=True,
    pool_pre_ping=True,
    connect_args={"connect_timeout": settings.POSTGRES_CONNECT_TIMEOUT},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
