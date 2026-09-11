from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "JobPilot AI"
    ENVIRONMENT: Literal["local", "test", "production"] = "local"
    DEBUG: bool = False
    API_PREFIX: str = "/api"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    SECRET_KEY: str

    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "jobpilot"
    POSTGRES_TEST_DB: str = "jobpilot_test"
    POSTGRES_CONNECT_TIMEOUT: int = 3

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool = False

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key_strength(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return value

    @field_validator("POSTGRES_CONNECT_TIMEOUT")
    @classmethod
    def validate_connect_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("POSTGRES_CONNECT_TIMEOUT must be a positive number of seconds")
        return value

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES", "REFRESH_TOKEN_EXPIRE_DAYS")
    @classmethod
    def validate_positive_token_lifetimes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("token lifetimes must be positive")
        return value

    @model_validator(mode="after")
    def validate_production_cookie_security(self) -> "Settings":
        if self.ENVIRONMENT == "production" and not self.AUTH_COOKIE_SECURE:
            raise ValueError(
                "AUTH_COOKIE_SECURE must be true when ENVIRONMENT is production"
            )
        return self

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def _postgres_url(self, database: str) -> str:
        return (
            f"postgresql+psycopg://{quote_plus(self.POSTGRES_USER)}:"
            f"{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{database}"
        )

    @property
    def database_url(self) -> str:
        return self._postgres_url(self.POSTGRES_DB)

    @property
    def test_database_url(self) -> str:
        return self._postgres_url(self.POSTGRES_TEST_DB)

    @property
    def database_url_masked(self) -> str:
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:***"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
