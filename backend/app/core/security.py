import secrets
import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.core.config import get_settings

REFRESH_COOKIE_NAME = "jobpilot_refresh"
CSRF_COOKIE_NAME = "jobpilot_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
JWT_ISSUER = "jobpilot-ai"
JWT_ALGORITHM = "HS256"

_password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = _password_hasher.hash("timing-equalizer-dummy-password")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


def dummy_verify() -> None:
    _password_hasher.verify("invalid-dummy-input", DUMMY_PASSWORD_HASH)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
        "iss": JWT_ISSUER,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["exp", "sub", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return uuid.UUID(payload["sub"])


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def set_auth_cookies(response: Response, settings, refresh_token: str, csrf_token: str) -> None:
    secure = getattr(settings, "AUTH_COOKIE_SECURE", False)
    max_age = getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 7) * 24 * 60 * 60
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max_age,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/api/auth",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="strict",
        secure=secure,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
