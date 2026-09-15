from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator, model_validator
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
    # Use a project-specific environment name because DEBUG is commonly set by
    # shells and developer tools to non-Boolean values.
    DEBUG: bool = Field(default=False, validation_alias="JOBPILOT_DEBUG")
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

    # The e2e support endpoints (bootstrap/cleanup) require an explicit,
    # disabled-by-default test mode. The endpoints additionally require a
    # dedicated test database (enforced inside the routes against
    # POSTGRES_TEST_DB), so both gates must be satisfied together. This flag is
    # False by default, which keeps the disposable-user/bootstrap surface
    # unreachable in every ordinary deployment.
    E2E_TEST_MODE: bool = False

    # Jira Cloud integration (create-only, disabled by default).
    # JIRA_ENABLED must be explicitly set to True before any request is made;
    # this stays False so the create-issuer is inert in every ordinary
    # deployment. The API token is read from the gitignored local .env only
    # (ATLASSIAN_API_TOKEN) and is never part of committed config.
    JIRA_ENABLED: bool = False
    JIRA_SITE_URL: str = ""
    JIRA_PROJECT_KEY: str = ""
    # The account email is the Basic-auth user id for Atlassian Cloud API
    # tokens (payload is ``email:token``); required only when Jira is enabled.
    JIRA_USER_EMAIL: str = ""
    JIRA_API_TOKEN: str = Field(default="", repr=False)

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool = False

    RESUME_STORAGE_DIR: str = str(BASE_DIR / "storage" / "resumes")
    RESUME_MAX_SIZE_MB: int = 10
    RESUME_EXTRACTION_TIMEOUT_SECONDS: int = 15
    RESUME_EXTRACTION_MAX_CHARS: int = 200_000
    RESUME_EXTRACTION_MAX_PAGES: int = 100
    RESUME_EXTRACTION_MAX_BLOCKS: int = 10_000

    JOBPILOT_AI_ENABLED: bool = False
    JOBPILOT_AI_PROVIDER: Literal["openai", "groq"] = "openai"
    JOBPILOT_AI_MODEL: str = "gpt-5-mini"
    JOBPILOT_OPENAI_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    JOBPILOT_GROQ_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    JOBPILOT_GROQ_MODEL: str = "openai/gpt-oss-20b"
    JOBPILOT_AI_TIMEOUT_SECONDS: int = 30
    JOBPILOT_AI_MAX_INPUT_CHARS: int = 100_000
    JOBPILOT_AI_MAX_OUTPUT_TOKENS: int = 4_000
    JOBPILOT_AI_MAX_REQUESTS_PER_USER: int = 20
    JOBPILOT_AI_TEST_PROVIDER: bool = False

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

    @field_validator(
        "RESUME_EXTRACTION_TIMEOUT_SECONDS",
        "RESUME_EXTRACTION_MAX_CHARS",
        "RESUME_EXTRACTION_MAX_PAGES",
        "RESUME_EXTRACTION_MAX_BLOCKS",
        "JOBPILOT_AI_TIMEOUT_SECONDS",
        "JOBPILOT_AI_MAX_INPUT_CHARS",
        "JOBPILOT_AI_MAX_OUTPUT_TOKENS",
        "JOBPILOT_AI_MAX_REQUESTS_PER_USER",
    )
    @classmethod
    def validate_extraction_limits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("resume extraction limits must be positive")
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
