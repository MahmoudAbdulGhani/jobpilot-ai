import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    dummy_verify,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import RefreshToken, User


class OwnerAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_first_owner(session: Session, *, email: str, password: str) -> User:
    if session.scalar(select(User)) is not None:
        raise OwnerAlreadyExistsError("an owner account already exists")
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, *, email: str, password: str) -> User:
    user = session.scalar(
        select(User).where(User.email == normalize_email(email))
    )
    if user is None:
        dummy_verify()
        raise InvalidCredentialsError
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    if not user.is_active:
        raise InvalidCredentialsError
    return user


def issue_session(session: Session, *, user: User) -> tuple[str, str]:
    refresh = generate_refresh_token()
    session.add(_refresh_row(user.id, refresh))
    session.commit()
    access = create_access_token(user.id)
    return access, refresh


def rotate_refresh(session: Session, *, presented: str) -> tuple[User, str, str]:
    row = _lookup_active(session, presented)
    if row is None:
        raise InvalidRefreshTokenError
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError
    row.revoked_at = datetime.now(timezone.utc)
    new_refresh = generate_refresh_token()
    session.add(_refresh_row(user.id, new_refresh))
    session.commit()
    return user, create_access_token(user.id), new_refresh


def revoke_presented(session: Session, *, presented: str) -> None:
    row = _lookup_active(session, presented)
    if row is not None:
        row.revoked_at = datetime.now(timezone.utc)
        session.commit()


def _refresh_row(user_id: uuid.UUID, token: str) -> RefreshToken:
    settings = get_settings()
    return RefreshToken(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def _lookup_active(session: Session, presented: str) -> RefreshToken | None:
    row = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(presented))
    )
    if row is None or not row.is_active():
        return None
    return row
