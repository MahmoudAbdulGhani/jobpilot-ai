from functools import lru_cache
from decimal import Decimal
from app.schemas.plans import PlanLimits
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote_plus, urlsplit
import os
import uuid

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    APP_NAME: str = "JobPilot AI"
    ACCOUNT_EXPORT_MAX_MIB: int = Field(default=25, ge=1, le=100)
    ACCOUNT_EXPORT_MAX_ROWS: int = Field(default=10000, ge=1, le=50000)
    ACCOUNT_EXPORT_MINUTES: int = Field(default=10, ge=1, le=10)
    ACCOUNT_TOKEN_RETENTION_DAYS: int = Field(default=1, ge=0, le=30)
    ACCOUNT_OPERATION_RETENTION_DAYS: int = Field(default=30, ge=1, le=365)
    ACCOUNT_EMAIL_PREVIEW_DAYS: int = Field(default=90, ge=1, le=3650)
    ENVIRONMENT: Literal["local", "test", "production"] = "local"
    # Use a project-specific environment name because DEBUG is commonly set by
    # shells and developer tools to non-Boolean values.
    DEBUG: bool = Field(default=False, validation_alias="JOBPILOT_DEBUG")
    API_PREFIX: str = "/api"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    SECRET_KEY: str = Field(repr=False, exclude=True)
    JOBPILOT_APP_URL: str = ""
    ALLOWED_HOSTS: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1", "testserver"]
    JOBPILOT_PROXY_IPS: str = ""
    POSTGRES_SSLMODE: Literal["disable", "require", "verify-full"] = "disable"
    POSTGRES_SSLROOTCERT: str = ""
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=20)
    DB_MAX_OVERFLOW: int = Field(default=0, ge=0, le=10)

    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5433
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = Field(repr=False, exclude=True)
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
    JOBPILOT_REGISTRATION: Literal["closed", "invite-only", "public"] = "invite-only"
    JOBPILOT_ACCOUNT_APP_URL: str = ""
    JOBPILOT_ACCOUNT_MAIL_TRANSPORT: Literal["disabled", "smtp", "test"] = "disabled"
    JOBPILOT_ACCOUNT_MAIL_FROM: str = ""
    JOBPILOT_ACCOUNT_SMTP_HOST: str = ""
    JOBPILOT_ACCOUNT_SMTP_PORT: int = 465
    JOBPILOT_ACCOUNT_SMTP_USER: str = Field(default="", repr=False)
    JOBPILOT_ACCOUNT_SMTP_PASSWORD: str = Field(default="", repr=False, exclude=True)
    JOBPILOT_DIGEST_MAIL_TRANSPORT: Literal["disabled", "smtp", "test"] = "disabled"
    JOBPILOT_DIGEST_MAIL_FROM: str = ""
    JOBPILOT_DIGEST_SMTP_HOST: str = ""
    JOBPILOT_DIGEST_SMTP_PORT: int = 465
    JOBPILOT_DIGEST_SMTP_USER: str = Field(default="", repr=False)
    JOBPILOT_DIGEST_SMTP_PASSWORD: str = Field(default="", repr=False, exclude=True)
    RESUME_STORAGE_DIR: str = str(BASE_DIR / "storage" / "resumes")
    JOBPILOT_STORAGE: Literal["local", "supabase"] = "local"
    JOBPILOT_STORAGE_URL: str = ""
    JOBPILOT_STORAGE_BUCKET: str = ""
    JOBPILOT_STORAGE_KEY: str = Field(default="", repr=False, exclude=True)
    RESUME_MAX_SIZE_MB: int = 10
    RESUME_EXTRACTION_TIMEOUT_SECONDS: int = 15
    RESUME_EXTRACTION_MAX_CHARS: int = 200_000
    RESUME_EXTRACTION_MAX_PAGES: int = 100
    RESUME_EXTRACTION_MAX_BLOCKS: int = 10_000

    JOBPILOT_AI_ENABLED: bool = False
    JOBPILOT_AI_PILOT_ENABLED: bool = False
    JOBPILOT_AI_PILOT_ACCOUNT_ID: str = ""
    JOBPILOT_QA_STRUCTURED_FALLBACK: bool = False
    JOBPILOT_GOOGLE_CLIENT_ID: str = Field(default="", repr=False, exclude=True)
    JOBPILOT_GOOGLE_CLIENT_SECRET: str = Field(default="", repr=False, exclude=True)
    JOBPILOT_GOOGLE_REDIRECT_URI: str = ""
    JOBPILOT_MAILBOX_SETTINGS_URL: str = ""
    JOBPILOT_MAILBOX_ENCRYPTION_KEY: str = Field(default="", repr=False, exclude=True)
    JOBPILOT_MAILBOX_TEST_PROVIDER: bool = False
    JOBPILOT_DISCOVERY_ENABLED: bool = True
    JOBPILOT_DISCOVERY_TEST_PROVIDER: bool = False
    JOBPILOT_AI_PROVIDER: Literal["openai", "groq"] = "openai"
    JOBPILOT_AI_MODEL: str = "gpt-5-mini"
    JOBPILOT_OPENAI_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    JOBPILOT_GROQ_API_KEY: str | None = Field(default=None, repr=False, exclude=True)
    JOBPILOT_GROQ_MODEL: str = "openai/gpt-oss-20b"
    JOBPILOT_AI_TIMEOUT_SECONDS: int = 30
    JOBPILOT_AI_MAX_INPUT_CHARS: int = 100_000
    JOBPILOT_AI_MAX_OUTPUT_TOKENS: int = 4_000
    JOBPILOT_OPENAI_PROFILE_MAX_OUTPUT_TOKENS: int = 12_000
    JOBPILOT_AI_MAX_REQUESTS_PER_USER: int = 20
    JOBPILOT_AI_TEST_PROVIDER: bool = False

    # Temporary diagnostic mode: when True, the production validator collects
    # all failures instead of raising on the first one. The entry point prints
    # the failing setting name and validation category, never the value.
    JOBPILOT_CONFIG_DIAGNOSTIC: bool = False

    JOBPILOT_PLAN_LIMITS: dict[str, PlanLimits] = {
        "free": PlanLimits(), "legacy": PlanLimits(),
        "invited_beta": PlanLimits(total=100), "paid": PlanLimits(total=200)}
    JOBPILOT_PLAN_ADMIN_EMAILS: Annotated[list[str], NoDecode] = []
    JOBPILOT_PROPOSED_MONTHLY_PRICE_USD: Decimal = Field(default=Decimal("8.00"), ge=0, le=10000)

    @field_validator("JOBPILOT_PLAN_LIMITS")
    @classmethod
    def plan_catalog(cls, value):
        if set(value) != {"free", "legacy", "invited_beta", "paid"}:
            raise ValueError("Configure exactly free, legacy, invited_beta and paid plan limits")
        return value

    @field_validator("JOBPILOT_PLAN_ADMIN_EMAILS", mode="before")
    @classmethod
    def plan_admins(cls, value):
        values = value.split(",") if isinstance(value, str) else value
        return [email.strip().lower() for email in values if email.strip()]

    # Packs have an independent, validated provider configuration.
    JOBPILOT_PACK_PROVIDER: Literal["openai"] = "openai"
    JOBPILOT_PACK_MODEL: str = "gpt-5-mini"
    JOBPILOT_PACK_REASONING_EFFORT: Literal["minimal", "low", "medium", "high"] = "minimal"
    JOBPILOT_PACK_MAX_OUTPUT_TOKENS: int = 10_000
    JOBPILOT_PACK_TIMEOUT_SECONDS: int = 90

    # Interview settings are independent of profile, fit and pack generation.
    JOBPILOT_INTERVIEW_PROVIDER: Literal["openai"] = "openai"
    JOBPILOT_INTERVIEW_MODEL: Literal["gpt-5-mini"] = "gpt-5-mini"
    JOBPILOT_INTERVIEW_REASONING_EFFORT: Literal["minimal", "low", "medium", "high"] = "minimal"
    JOBPILOT_INTERVIEW_MAX_OUTPUT_TOKENS: int = Field(default=2000, ge=500, le=4000)
    JOBPILOT_INTERVIEW_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=120)
    JOBPILOT_INTERVIEW_MAX_INPUT_BYTES: int = Field(default=32000, ge=8000, le=64000)
    JOBPILOT_INTERVIEW_MAX_CALLS_PER_SESSION: int = Field(default=10, ge=3, le=14)
    JOBPILOT_INTERVIEW_MAX_SESSIONS_PER_USER: int = Field(default=20, ge=1, le=100)

    # Optional speech input/output only. Existing AI configurations are unchanged.
    JOBPILOT_VOICE_ENABLED: bool = False
    JOBPILOT_LIVE_VOICE_ENABLED: bool = False
    JOBPILOT_LIVE_VOICE_MODEL: Literal["gpt-realtime-2.1"] = "gpt-realtime-2.1"
    JOBPILOT_LIVE_VOICE_MAX_MINUTES: int = Field(default=10, ge=1, le=10)

    @field_validator("JOBPILOT_AI_PILOT_ACCOUNT_ID")
    @classmethod
    def valid_pilot_account(cls, value: str) -> str:
        if value:
            uuid.UUID(value)
        return value
    JOBPILOT_VOICE_PROVIDER: Literal["openai"] = "openai"
    JOBPILOT_VOICE_TRANSCRIPTION_MODEL: Literal["whisper-1"] = "whisper-1"
    JOBPILOT_VOICE_SPEECH_MODEL: Literal["tts-1"] = "tts-1"
    JOBPILOT_VOICE_API_KEY: str = Field(default="", repr=False, exclude=True)
    JOBPILOT_VOICE_TEST_PROVIDER: bool = False
    JOBPILOT_VOICE_MAX_SECONDS: int = Field(default=60, ge=1, le=60)
    JOBPILOT_VOICE_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=60)
    JOBPILOT_VOICE_MAX_CALLS_PER_SESSION: int = Field(default=18, ge=1, le=30)
    JOBPILOT_VOICE_TRANSCRIPT_MINUTES: int = Field(default=10, ge=1, le=60)

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
        "JOBPILOT_OPENAI_PROFILE_MAX_OUTPUT_TOKENS",
        "JOBPILOT_AI_MAX_REQUESTS_PER_USER",
        "JOBPILOT_PACK_MAX_OUTPUT_TOKENS",
        "JOBPILOT_PACK_TIMEOUT_SECONDS",
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

    _production_failures: list[dict] = []

    @model_validator(mode="after")
    def validate_production_cookie_security(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        import re

        def origin(value):
            u = urlsplit(value)
            try:
                port = u.port
            except ValueError:
                return False
            if port not in {None, 443}:
                return False
            return (
                u.scheme == "https"
                and bool(u.hostname)
                and u.hostname not in {"localhost", "127.0.0.1"}
                and not u.username
                and not u.password
                and not u.query
                and not u.fragment
                and u.path in {"", "/"}
            )

        failures: list[dict] = []

        def _check(setting, category, ok, message=""):
            if not ok:
                failures.append({"setting": setting, "category": category, "message": message})

        # --- cookie ---
        _check("AUTH_COOKIE_SECURE", "cookie_security",
               self.AUTH_COOKIE_SECURE,
               "AUTH_COOKIE_SECURE must be true when ENVIRONMENT is production")

        # --- test providers / debug ---
        _check("DEBUG", "forbidden_flags", not self.DEBUG)
        _check("E2E_TEST_MODE", "forbidden_flags", not self.E2E_TEST_MODE)
        _check("JOBPILOT_AI_TEST_PROVIDER", "forbidden_flags", not self.JOBPILOT_AI_TEST_PROVIDER)
        _check("JOBPILOT_MAILBOX_TEST_PROVIDER", "forbidden_flags", not self.JOBPILOT_MAILBOX_TEST_PROVIDER)
        _check("JOBPILOT_DISCOVERY_TEST_PROVIDER", "forbidden_flags", not self.JOBPILOT_DISCOVERY_TEST_PROVIDER)
        _check("JOBPILOT_VOICE_TEST_PROVIDER", "forbidden_flags", not self.JOBPILOT_VOICE_TEST_PROVIDER)
        _check("JOBPILOT_AI_PILOT_ENABLED", "ai_pilot",
               not self.JOBPILOT_AI_PILOT_ENABLED or (
                   self.JOBPILOT_AI_ENABLED
                   and bool(self.JOBPILOT_AI_PILOT_ACCOUNT_ID)
                   and self.JOBPILOT_AI_PROVIDER == "openai"))
        _check("JOBPILOT_ACCOUNT_MAIL_TRANSPORT", "forbidden_flags",
               self.JOBPILOT_ACCOUNT_MAIL_TRANSPORT != "test")
        _check("JOBPILOT_DIGEST_MAIL_TRANSPORT", "forbidden_flags",
               self.JOBPILOT_DIGEST_MAIL_TRANSPORT != "test")

        # --- origins / hosts ---
        _check("JOBPILOT_APP_URL", "app_origin",
               origin(self.JOBPILOT_APP_URL) and self.CORS_ORIGINS == [self.JOBPILOT_APP_URL.rstrip('/')],
               "JOBPILOT_APP_URL must be a valid HTTPS origin and match CORS_ORIGINS")
        _check("ALLOWED_HOSTS", "allowed_hosts",
               self.ALLOWED_HOSTS
               and all(
                   re.fullmatch(r"[a-zA-Z0-9.-]+", h) and h not in {"localhost", "127.0.0.1", "testserver"}
                   for h in self.ALLOWED_HOSTS
               ),
               "ALLOWED_HOSTS must contain explicit hostnames, no localhost/testserver")
        hostname = urlsplit(self.JOBPILOT_APP_URL).hostname
        _check("JOBPILOT_APP_URL", "allowed_hosts",
               hostname in self.ALLOWED_HOSTS,
               "JOBPILOT_APP_URL hostname must appear in ALLOWED_HOSTS")

        # --- database ---
        _check("POSTGRES_HOST", "database_target",
               self.POSTGRES_HOST not in {"localhost", "127.0.0.1", ""},
               "POSTGRES_HOST must not be localhost or empty in production")
        _check("POSTGRES_DB", "database_target",
               self.POSTGRES_DB != self.POSTGRES_TEST_DB,
               "POSTGRES_DB must differ from POSTGRES_TEST_DB")
        _check("POSTGRES_PASSWORD", "database_tls",
               bool(self.POSTGRES_PASSWORD))
        _check("POSTGRES_SSLMODE", "database_tls",
               self.POSTGRES_SSLMODE == "verify-full",
               "POSTGRES_SSLMODE must be verify-full in production")
        _check("POSTGRES_SSLROOTCERT", "database_tls",
               bool(self.POSTGRES_SSLROOTCERT) and Path(self.POSTGRES_SSLROOTCERT).is_file(),
               "POSTGRES_SSLROOTCERT must point to an existing CA file on disk")

        # --- proxy ---
        if self.JOBPILOT_PROXY_IPS:
            from ipaddress import ip_network
            proxy_ok = True
            try:
                for entry in self.JOBPILOT_PROXY_IPS.split(","):
                    network = ip_network(entry.strip())
                    if network.prefixlen < (8 if network.version == 4 else 32):
                        proxy_ok = False
            except ValueError:
                proxy_ok = False
            _check("JOBPILOT_PROXY_IPS", "proxy_trust", proxy_ok,
                   "JOBPILOT_PROXY_IPS must contain explicit IP addresses or CIDR networks")

        # --- secret key strength ---
        _check("SECRET_KEY", "secret_key",
               len(set(self.SECRET_KEY)) >= 12
               and not any(w in self.SECRET_KEY.lower() for w in ("change-me", "changeme", "example", "test-secret")),
               "SECRET_KEY must have >= 12 distinct characters and no weak words")

        # --- storage ---
        _check("JOBPILOT_STORAGE", "object_storage",
               self.JOBPILOT_STORAGE == "supabase",
               "JOBPILOT_STORAGE must be supabase in production")
        _check("JOBPILOT_STORAGE_URL", "object_storage",
               origin(self.JOBPILOT_STORAGE_URL),
               "JOBPILOT_STORAGE_URL must be a valid HTTPS origin")
        _check("JOBPILOT_STORAGE_KEY", "object_storage",
               bool(self.JOBPILOT_STORAGE_KEY),
               "JOBPILOT_STORAGE_KEY must be non-empty")
        _check("JOBPILOT_STORAGE_BUCKET", "object_storage",
               bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", self.JOBPILOT_STORAGE_BUCKET)),
               "JOBPILOT_STORAGE_BUCKET must match [a-z0-9][a-z0-9-]{0,62}")

        # --- account email ---
        if self.JOBPILOT_ACCOUNT_MAIL_TRANSPORT != "disabled":
            _check("JOBPILOT_ACCOUNT_MAIL_TRANSPORT", "account_email",
                   self.JOBPILOT_ACCOUNT_APP_URL.rstrip("/") == self.JOBPILOT_APP_URL.rstrip("/")
                   and bool(self.JOBPILOT_ACCOUNT_SMTP_HOST)
                   and bool(self.JOBPILOT_ACCOUNT_MAIL_FROM),
                   "Account email requires matching APP_URL, SMTP host, and sender")

        # --- digest smtp ---
        if self.JOBPILOT_DIGEST_MAIL_TRANSPORT == "smtp":
            _check("JOBPILOT_DIGEST_SMTP_HOST", "digest_smtp",
                   bool(self.JOBPILOT_DIGEST_SMTP_HOST) and bool(self.JOBPILOT_DIGEST_MAIL_FROM),
                   "Digest SMTP requires a host and from address")

        # --- gmail / mailbox redirects ---
        if any((self.JOBPILOT_GOOGLE_CLIENT_ID, self.JOBPILOT_GOOGLE_CLIENT_SECRET, self.JOBPILOT_MAILBOX_ENCRYPTION_KEY)):
            base = self.JOBPILOT_APP_URL.rstrip("/")
            _check("JOBPILOT_GOOGLE_REDIRECT_URI", "mailbox_redirects",
                   self.JOBPILOT_GOOGLE_REDIRECT_URI == base + "/api/mailboxes/oauth/callback",
                   "JOBPILOT_GOOGLE_REDIRECT_URI must use the trusted application origin")
            _check("JOBPILOT_MAILBOX_SETTINGS_URL", "mailbox_redirects",
                   self.JOBPILOT_MAILBOX_SETTINGS_URL == base + "/settings",
                   "JOBPILOT_MAILBOX_SETTINGS_URL must use the trusted application origin")

        if self.JOBPILOT_CONFIG_DIAGNOSTIC:
            self._production_failures = failures
            return self

        if failures:
            first = failures[0]
            raise ValueError(f"{first['category']}: {first['message']}")
        return self

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def split_cors_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def _postgres_url(self, database: str) -> str:
        base = (
            f"postgresql+psycopg://{quote_plus(self.POSTGRES_USER)}:"
            f"{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{database}"
        )
        if self.POSTGRES_SSLMODE != "disable":
            base += "?sslmode=" + self.POSTGRES_SSLMODE
            if self.POSTGRES_SSLROOTCERT: base += "&sslrootcert=" + quote_plus(self.POSTGRES_SSLROOTCERT)
        return base

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
    # Production/test never implicitly read a developer's .env file.
    try:
        mode = os.environ.get("ENVIRONMENT", "local")
        settings = Settings(_env_file=None if mode in {"production", "test"} else str(BASE_DIR / ".env"))
        if settings.ENVIRONMENT != mode: raise ValueError()
        return settings
    except Exception:
        raise RuntimeError("Invalid application configuration; validate required settings using the deployment runbook") from None
