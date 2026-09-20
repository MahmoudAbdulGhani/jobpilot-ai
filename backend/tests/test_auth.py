import contextlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import (
    CSRF_COOKIE_NAME,
    JWT_ALGORITHM,
    JWT_ISSUER,
    REFRESH_COOKIE_NAME,
    generate_csrf_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    set_auth_cookies,
)
from app.models import RefreshToken, User
from app.services import auth_service

TEST_PASSWORD = "correct-horse-battery-staple"
GENERIC_LOGIN_DETAIL = "Incorrect email or password"
GENERIC_TOKEN_DETAIL = "Could not validate credentials"
GENERIC_REFRESH_DETAIL = "Invalid refresh token"


@pytest.fixture()
def owner(db_session):
    user = User(
        email="owner@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_client(client, db_session):
    def override():
        yield db_session

    client.app.dependency_overrides[get_db] = override
    yield client
    client.app.dependency_overrides.pop(get_db, None)


def make_token(user_id, *, key=None, expires_delta=timedelta(minutes=5), token_type="access") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type,
        "iss": JWT_ISSUER,
    }
    return pyjwt.encode(payload, key or get_settings().SECRET_KEY, algorithm=JWT_ALGORITHM)


def client_cookie_value(*, client: TestClient, name: str) -> str | None:
    return client.cookies.get(name)


def login(auth_client, email="owner@jobpilot-test.com", password=TEST_PASSWORD):
    return auth_client.post("/api/auth/login", json={"email": email, "password": password})


def csrf_header_from(client) -> dict:
    token = client.cookies.get(CSRF_COOKIE_NAME)
    return {"X-CSRF-Token": token} if token else {}


class TestOwnerSetupService:
    def test_create_first_owner_hashes_and_normalizes(self, db_session):
        user = auth_service.create_first_owner(
            db_session, email="  Owner@jobpilot-test.com ", password=TEST_PASSWORD
        )
        assert user.email == "owner@jobpilot-test.com"
        assert user.password_hash.startswith("$argon2")
        assert TEST_PASSWORD not in user.password_hash
        assert user.is_active is True

    def test_second_owner_refused(self, db_session):
        auth_service.create_first_owner(db_session, email="a@jobpilot-test.com", password=TEST_PASSWORD)
        with pytest.raises(auth_service.OwnerAlreadyExistsError):
            auth_service.create_first_owner(db_session, email="b@jobpilot-test.com", password=TEST_PASSWORD)
        assert db_session.scalar(select(func.count(User.id))) == 1


class TestLogin:
    def test_success_returns_access_token_and_sets_cookies(self, auth_client, owner):
        response = login(auth_client)
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["token_type"] == "bearer"
        assert len(body["access_token"].split(".")) == 3
        assert body["expires_in"] == 900

        set_cookies = response.headers.get_list("set-cookie")
        refresh_line = next(line for line in set_cookies if line.startswith(f"{REFRESH_COOKIE_NAME}="))
        csrf_line = next(line for line in set_cookies if line.startswith(f"{CSRF_COOKIE_NAME}="))

        assert "httponly" in refresh_line.lower()
        assert "samesite=strict" in refresh_line.lower()
        assert "path=/api/auth" in refresh_line.lower()
        assert "secure" not in refresh_line.lower()
        assert "httponly" not in csrf_line.lower()
        assert "samesite=strict" in csrf_line.lower()

    def test_login_accepts_mixed_case_email(self, auth_client, owner):
        assert login(auth_client, email="OWNER@jobpilot-test.com").status_code == status.HTTP_200_OK

    def test_unknown_email_generic_response(self, auth_client, owner):
        response = login(auth_client, email="ghost@jobpilot-test.com")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": GENERIC_LOGIN_DETAIL}

    def test_wrong_password_identical_generic_response(self, auth_client, owner):
        wrong = login(auth_client, password="not-the-password-123")
        unknown = login(auth_client, email="ghost@jobpilot-test.com")
        assert wrong.status_code == unknown.status_code
        assert wrong.json() == unknown.json()
        assert wrong.json() == {"detail": GENERIC_LOGIN_DETAIL}

    def test_inactive_owner_rejected_with_generic_response(self, auth_client, db_session):
        db_session.add(
            User(
                email="inactive@jobpilot-test.com",
                password_hash=hash_password(TEST_PASSWORD),
                is_active=False,
            )
        )
        db_session.commit()
        response = login(auth_client, email="inactive@jobpilot-test.com")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": GENERIC_LOGIN_DETAIL}


class TestAccessTokenAuthentication:
    def test_me_requires_token(self, auth_client, owner):
        response = auth_client.get("/api/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": GENERIC_TOKEN_DETAIL}

    def test_me_with_valid_token(self, auth_client, owner):
        access = login(auth_client).json()["access_token"]
        response = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["email"] == "owner@jobpilot-test.com"
        assert uuid.UUID(response.json()["id"]) == owner.id
        assert response.json()["is_active"] is True

    def test_malformed_token_rejected(self, auth_client, owner):
        response = auth_client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": GENERIC_TOKEN_DETAIL}

    def test_expired_token_rejected(self, auth_client, owner):
        expired = make_token(owner.id, expires_delta=timedelta(seconds=-30))
        response = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_signature_rejected(self, auth_client, owner):
        forged = make_token(owner.id, key="attacker-controlled-signing-key")
        response = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_token_type_rejected(self, auth_client, owner):
        refresh_typed = make_token(owner.id, token_type="refresh")
        response = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {refresh_typed}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_deactivated_after_login_rejected_on_me(self, auth_client, db_session, owner):
        access = login(auth_client).json()["access_token"]
        owner.is_active = False
        db_session.commit()
        response = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRefreshRotation:
    def test_refresh_success_rotates_token(self, auth_client, owner, db_session):
        login(auth_client)
        old_refresh = client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME)
        old_row = db_session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(old_refresh))
        )

        response = auth_client.post("/api/auth/refresh", headers=csrf_header_from(auth_client))

        assert response.status_code == status.HTTP_200_OK
        new_refresh = client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME)
        assert new_refresh != old_refresh

        db_session.refresh(old_row)
        assert old_row.revoked_at is not None
        assert db_session.scalar(select(func.count(RefreshToken.id))) == 2

        new_row = db_session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(new_refresh))
        )
        assert new_row is not None
        assert new_row.revoked_at is None

    def test_replayed_refresh_rejected(self, auth_client, owner):
        login(auth_client)
        old_refresh = client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME)
        old_csrf = client_cookie_value(client=auth_client, name=CSRF_COOKIE_NAME)

        assert (
            auth_client.post("/api/auth/refresh", headers={"X-CSRF-Token": old_csrf}).status_code
            == status.HTTP_200_OK
        )

        replay = auth_client.post(
            "/api/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: old_refresh, CSRF_COOKIE_NAME: old_csrf},
            headers={"X-CSRF-Token": old_csrf},
        )
        assert replay.status_code == status.HTTP_401_UNAUTHORIZED
        assert replay.json() == {"detail": GENERIC_REFRESH_DETAIL}

    def test_missing_refresh_cookie_rejected(self, auth_client, owner):
        csrf = generate_csrf_token()
        response = auth_client.post(
            "/api/auth/refresh",
            cookies={CSRF_COOKIE_NAME: csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": GENERIC_REFRESH_DETAIL}

    def test_expired_refresh_token_rejected(self, auth_client, owner, db_session):
        presented = generate_refresh_token()
        db_session.add(
            RefreshToken(
                user_id=owner.id,
                token_hash=hash_token(presented),
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        db_session.commit()
        csrf = generate_csrf_token()
        response = auth_client.post(
            "/api/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: presented, CSRF_COOKIE_NAME: csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unknown_refresh_token_rejected(self, auth_client, owner):
        csrf = generate_csrf_token()
        response = auth_client.post(
            "/api/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: generate_refresh_token(), CSRF_COOKIE_NAME: csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestCsrfEnforcement:
    def test_missing_csrf_header_rejected(self, auth_client, owner):
        login(auth_client)
        response = auth_client.post("/api/auth/refresh")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"detail": "CSRF check failed"}

    def test_wrong_csrf_value_rejected(self, auth_client, owner):
        login(auth_client)
        response = auth_client.post(
            "/api/auth/refresh",
            cookies={CSRF_COOKIE_NAME: "legit-value"},
            headers={"X-CSRF-Token": "forged-value"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_no_cookies_at_all_rejected_as_csrf(self, auth_client, owner):
        response = auth_client.post("/api/auth/refresh")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestLogout:
    def test_logout_requires_bearer_token(self, auth_client, owner, db_session):
        login(auth_client)
        refresh = client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME)
        csrf = client_cookie_value(client=auth_client, name=CSRF_COOKIE_NAME)

        response = auth_client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": csrf}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        row = db_session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh))
        )
        db_session.refresh(row)
        assert row.revoked_at is None

    def test_logout_revokes_and_clears_cookies(self, auth_client, owner, db_session):
        login_response = login(auth_client)
        access = login_response.json()["access_token"]
        old_refresh = client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME)
        old_csrf = client_cookie_value(client=auth_client, name=CSRF_COOKIE_NAME)

        response = auth_client.post(
            "/api/auth/logout",
            headers={
                "Authorization": f"Bearer {access}",
                "X-CSRF-Token": old_csrf,
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "logged_out"}

        set_cookies = response.headers.get_list("set-cookie")
        refresh_line = next(line for line in set_cookies if line.startswith(f"{REFRESH_COOKIE_NAME}="))
        csrf_line = next(line for line in set_cookies if line.startswith(f"{CSRF_COOKIE_NAME}="))
        assert 'max-age=0' in refresh_line.lower()
        assert 'max-age=0' in csrf_line.lower()

        row = db_session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(old_refresh))
        )
        db_session.refresh(row)
        assert row.revoked_at is not None

        replay = auth_client.post(
            "/api/auth/refresh",
            cookies={REFRESH_COOKIE_NAME: old_refresh, CSRF_COOKIE_NAME: old_csrf},
            headers={"X-CSRF-Token": old_csrf},
        )
        assert replay.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_without_csrf_fails(self, auth_client, owner):
        access = login(auth_client).json()["access_token"]
        response = auth_client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {access}"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_logout_does_not_revoke_another_users_refresh_token(
        self, auth_client, owner, db_session
    ):
        access = login(auth_client).json()["access_token"]
        other = User(
            email="other@jobpilot-test.com",
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        _, other_refresh = auth_service.issue_session(db_session, user=other)
        csrf = generate_csrf_token()

        response = auth_client.post(
            "/api/auth/logout",
            headers={
                "Authorization": f"Bearer {access}",
                "X-CSRF-Token": csrf,
            },
            cookies={
                REFRESH_COOKIE_NAME: other_refresh,
                CSRF_COOKIE_NAME: csrf,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        row = db_session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_token(other_refresh)
            )
        )
        db_session.refresh(row)
        assert row.revoked_at is None

    def test_logout_with_invalid_refresh_token_is_idempotent(
        self, auth_client, owner
    ):
        access = login(auth_client).json()["access_token"]
        csrf = generate_csrf_token()

        response = auth_client.post(
            "/api/auth/logout",
            headers={
                "Authorization": f"Bearer {access}",
                "X-CSRF-Token": csrf,
            },
            cookies={
                REFRESH_COOKIE_NAME: generate_refresh_token(),
                CSRF_COOKIE_NAME: csrf,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "logged_out"}

    def test_logout_with_already_revoked_token_is_idempotent(
        self, auth_client, owner, db_session
    ):
        login_response = login(auth_client)
        access = login_response.json()["access_token"]
        refresh = client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME)
        csrf = client_cookie_value(client=auth_client, name=CSRF_COOKIE_NAME)
        row = db_session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh))
        )
        row.revoked_at = datetime.now(timezone.utc)
        db_session.commit()

        response = auth_client.post(
            "/api/auth/logout",
            headers={
                "Authorization": f"Bearer {access}",
                "X-CSRF-Token": csrf,
            },
            cookies={REFRESH_COOKIE_NAME: refresh, CSRF_COOKIE_NAME: csrf},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "logged_out"}


class TestCookieFlags:
    def set_cookies_with(self, secure: bool) -> list[str]:
        from starlette.responses import Response

        settings_stub = SimpleNamespace(AUTH_COOKIE_SECURE=secure, REFRESH_TOKEN_EXPIRE_DAYS=7)
        response = Response()
        set_auth_cookies(response, settings_stub, refresh_token="r-token", csrf_token="c-token")
        return [
            value.decode("latin-1")
            for key, value in response.raw_headers
            if key == b"set-cookie"
        ]

    def test_local_http_configuration_has_no_secure_flag(self):
        refresh_line = next(line for line in self.set_cookies_with(False) if "r-token" in line)
        assert "httponly" in refresh_line.lower()
        assert "samesite=strict" in refresh_line.lower()
        assert "path=/api/auth" in refresh_line.lower()
        assert "secure" not in refresh_line.lower()

    def test_production_configuration_sets_secure_flag(self):
        lines = self.set_cookies_with(True)
        refresh_line = next(line for line in lines if "r-token" in line)
        csrf_line = next(line for line in lines if "c-token" in line)
        assert "secure" in refresh_line.lower()
        assert "secure" in csrf_line.lower()


class TestAuthenticationConfiguration:
    def base_kwargs(self, **overrides) -> dict:
        kwargs = dict(
            ENVIRONMENT="production",
            SECRET_KEY="x" * 48,
            POSTGRES_USER="jobpilot",
            POSTGRES_PASSWORD="secret",
            AUTH_COOKIE_SECURE=True,
            _env_file=None,
        )
        kwargs.update(overrides)
        return kwargs

    def test_production_without_secure_cookie_fails_fast(self):
        with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
            Settings(**self.base_kwargs(AUTH_COOKIE_SECURE=False))

    def test_zero_access_token_lifetime_fails_fast(self):
        with pytest.raises(ValidationError):
            Settings(**self.base_kwargs(ACCESS_TOKEN_EXPIRE_MINUTES=0))

    def test_negative_refresh_lifetime_fails_fast(self):
        with pytest.raises(ValidationError):
            Settings(**self.base_kwargs(REFRESH_TOKEN_EXPIRE_DAYS=-1))

    def test_secure_cookie_alone_is_not_complete_production_configuration(self):
        with pytest.raises(ValidationError, match="JOBPILOT_APP_URL must be a valid HTTPS origin"):
            Settings(**self.base_kwargs())


class TestSecretSanitization:
    def test_failed_login_never_logs_password_or_leaks_details(
        self, caplog, auth_client, owner
    ):
        marker_password = "leak-marker-super-secret-password"
        with caplog.at_level(logging.DEBUG):
            response = login(auth_client, password=marker_password)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert marker_password not in caplog.text
        assert response.json() == {"detail": GENERIC_LOGIN_DETAIL}

    def test_successful_flow_never_logs_tokens(self, caplog, auth_client, owner):
        with caplog.at_level(logging.DEBUG):
            login_response = login(auth_client)
            body = login_response.json()
            csrf = client_cookie_value(client=auth_client, name=CSRF_COOKIE_NAME)
            refresh_response = auth_client.post(
                "/api/auth/refresh", headers={"X-CSRF-Token": csrf}
            )
            me_response = auth_client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {refresh_response.json()['access_token']}"},
            )

        assert me_response.status_code == status.HTTP_200_OK
        assert body["access_token"][:24] not in caplog.text
        assert client_cookie_value(client=auth_client, name=REFRESH_COOKIE_NAME) not in caplog.text
        assert csrf not in caplog.text
