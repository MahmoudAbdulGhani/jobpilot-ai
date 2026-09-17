import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    decode_access_claims,
    generate_csrf_token,
    set_auth_cookies,
)
from app.models import User
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from app.services import auth_service
from app.services.auth_service import InvalidCredentialsError, InvalidRefreshTokenError

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer_scheme = HTTPBearer(auto_error=False)

GENERIC_LOGIN_DETAIL = "Incorrect email or password"
GENERIC_TOKEN_DETAIL = "Could not validate credentials"
GENERIC_REFRESH_DETAIL = "Invalid refresh token"
CSRF_DETAIL = "CSRF check failed"


def _require_bearer_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_TOKEN_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_claims(credentials.credentials)
        user_id = uuid.UUID(claims["sub"])
    except Exception:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_TOKEN_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, user_id)
    if user is None or not user.is_active or not user.email_verified or claims.get("session_version", 0) != user.session_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=GENERIC_TOKEN_DETAIL)
    return user


def _enforce_csrf(request: Request) -> None:
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if (
        not cookie_value
        or not header_value
        or not secrets.compare_digest(cookie_value, header_value)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=CSRF_DETAIL)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    settings = get_settings()
    try:
        user = auth_service.authenticate(db, email=body.email, password=body.password)
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_DETAIL)
    access, refresh = auth_service.issue_session(db, user=user)
    set_auth_cookies(
        response,
        settings,
        refresh_token=refresh,
        csrf_token=generate_csrf_token(),
    )
    return TokenResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    _enforce_csrf(request)
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if presented:
        try:
            _, access, new_refresh = auth_service.rotate_refresh(db, presented=presented)
        except InvalidRefreshTokenError:
            clear_auth_cookies(response)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=GENERIC_REFRESH_DETAIL)
        set_auth_cookies(
            response,
            get_settings(),
            refresh_token=new_refresh,
            csrf_token=generate_csrf_token(),
        )
        return TokenResponse(
            access_token=access,
            expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    clear_auth_cookies(response)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=GENERIC_REFRESH_DETAIL)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_bearer_user),
) -> dict:
    _enforce_csrf(request)
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if presented:
        auth_service.revoke_presented(
            db, presented=presented, user_id=current_user.id
        )
    clear_auth_cookies(response)
    return {"status": "logged_out"}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(_require_bearer_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        is_active=current_user.is_active, onboarding_step=current_user.onboarding_step,
    )
