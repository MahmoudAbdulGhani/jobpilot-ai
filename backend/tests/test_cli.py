import contextlib
import getpass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.cli import MIN_PASSWORD_LENGTH, main, prompt_credentials, prompt_password, resolve_local_disposable_database
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models import RefreshToken, User

TEST_PASSWORD = "a-very-long-test-password"


def session_factory(session):
    @contextlib.contextmanager
    def factory():
        yield session

    return factory


class TestSetupOwnerCli:
    def test_creates_first_owner(self, db_session, monkeypatch):
        monkeypatch.setattr("app.cli.SessionLocal", session_factory(db_session))
        monkeypatch.setattr(
            "app.cli.prompt_credentials",
            lambda: ("Owner@jobpilot-test.com", TEST_PASSWORD),
        )
        assert main(["setup-owner"]) == 0
        user = db_session.scalar(select(User))
        assert user.email == "owner@jobpilot-test.com"
        assert user.password_hash.startswith("$argon2")
        assert TEST_PASSWORD not in user.password_hash
        assert user.is_active is True

    def test_refuses_second_owner(self, db_session, monkeypatch):
        monkeypatch.setattr("app.cli.SessionLocal", session_factory(db_session))
        monkeypatch.setattr(
            "app.cli.prompt_credentials",
            lambda: ("first@jobpilot-test.com", TEST_PASSWORD),
        )
        assert main(["setup-owner"]) == 0
        monkeypatch.setattr(
            "app.cli.prompt_credentials",
            lambda: ("second@jobpilot-test.com", TEST_PASSWORD),
        )
        assert main(["setup-owner"]) == 1
        assert db_session.scalar(select(func.count(User.id))) == 1


class TestPromptCredentials:
    def patch_prompts(self, monkeypatch, email: str, passwords: list[str]):
        monkeypatch.setattr("builtins.input", lambda *args: email)
        responses = iter(passwords)
        monkeypatch.setattr(getpass, "getpass", lambda *args: next(responses))

    def test_happy_path_returns_credentials(self, monkeypatch):
        self.patch_prompts(
            monkeypatch,
            "owner@jobpilot-test.com",
            ["long-enough-password", "long-enough-password"],
        )
        email, password = prompt_credentials()
        assert email == "owner@jobpilot-test.com"
        assert password == "long-enough-password"

    def test_short_password_rejected(self, monkeypatch):
        self.patch_prompts(monkeypatch, "owner@jobpilot-test.com", ["short", "short"])
        with pytest.raises(SystemExit) as excinfo:
            prompt_credentials()
        assert excinfo.value.code == 1

    def test_mismatched_confirmation_rejected(self, monkeypatch):
        self.patch_prompts(
            monkeypatch,
            "owner@jobpilot-test.com",
            ["long-enough-password", "different-long-password"],
        )
        with pytest.raises(SystemExit) as excinfo:
            prompt_credentials()
        assert excinfo.value.code == 1

    def test_invalid_email_reprompts_then_accepts(self, monkeypatch):
        emails = iter(["not-an-email", "", "owner@jobpilot-test.com"])
        monkeypatch.setattr("builtins.input", lambda *args: next(emails))
        prompts = iter(["long-enough-password", "long-enough-password"])
        monkeypatch.setattr(getpass, "getpass", lambda *args: next(prompts))
        email, password = prompt_credentials()
        assert email == "owner@jobpilot-test.com"


class TestPromptPassword:
    def test_returns_confirmed_password(self, monkeypatch):
        monkeypatch.setattr(getpass, "getpass", lambda *args: "new-long-test-password")
        assert prompt_password() == "new-long-test-password"

    def test_short_password_rejected(self, monkeypatch):
        monkeypatch.setattr(getpass, "getpass", lambda *args: "short")
        with pytest.raises(SystemExit) as excinfo:
            prompt_password()
        assert excinfo.value.code == 1

    def test_mismatched_confirmation_rejected(self, monkeypatch):
        responses = iter(["long-enough-password", "different-long-password"])
        monkeypatch.setattr(getpass, "getpass", lambda *args: next(responses))
        with pytest.raises(SystemExit) as excinfo:
            prompt_password()
        assert excinfo.value.code == 1


class TestResetPasswordCli:
    NEW_PASSWORD = "a-new-long-test-password"

    def make_user(self, db_session, *, email="lockout@jobpilot-test.com"):
        user = User(
            email=email,
            password_hash=hash_password(TEST_PASSWORD),
            is_active=True,
            email_verified=True,
        )
        db_session.add(user)
        db_session.flush()
        for i in range(2):
            db_session.add(
                RefreshToken(
                    user_id=user.id,
                    token_hash=f"reset-password-token-{i}",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                )
            )
        db_session.commit()
        db_session.refresh(user)
        return user

    def patch_cli(self, db_session, monkeypatch):
        monkeypatch.setattr("app.cli.SessionLocal", session_factory(db_session))
        monkeypatch.setattr(getpass, "getpass", lambda *args: self.NEW_PASSWORD)

    def test_resets_password_and_invalidates_sessions(self, db_session, monkeypatch):
        user = self.make_user(db_session)
        self.patch_cli(db_session, monkeypatch)

        assert main(["reset-password", "--email", "LOCKOUT@jobpilot-test.com"]) == 0

        db_session.refresh(user)
        assert verify_password(self.NEW_PASSWORD, user.password_hash)
        assert not verify_password(TEST_PASSWORD, user.password_hash)
        assert user.session_version == 1
        tokens = db_session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        ).all()
        assert len(tokens) == 2
        assert all(token.revoked_at is not None for token in tokens)

    def test_only_password_fields_change(self, db_session, monkeypatch):
        user = self.make_user(db_session)
        original_email = user.email
        self.patch_cli(db_session, monkeypatch)

        assert main(["reset-password", "--email", user.email]) == 0
        db_session.refresh(user)
        assert user.email == original_email
        assert user.is_active is True
        assert user.email_verified is True
        assert db_session.scalar(select(func.count(User.id))) == 1

    def test_unknown_email_refused(self, db_session, monkeypatch):
        self.patch_cli(db_session, monkeypatch)
        assert main(["reset-password", "--email", "missing@jobpilot-test.com"]) == 1
        assert db_session.scalar(select(func.count(User.id))) == 0

    def test_inactive_user_refused(self, db_session, monkeypatch):
        user = User(email="inactive@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD), is_active=False)
        db_session.add(user)
        db_session.commit()
        self.patch_cli(db_session, monkeypatch)

        assert main(["reset-password", "--email", user.email]) == 1
        db_session.refresh(user)
        assert not verify_password(self.NEW_PASSWORD, user.password_hash)

    def test_refuses_in_production(self, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.cli.get_settings",
            lambda: get_settings().model_copy(update={"ENVIRONMENT": "production"}),
        )
        self.patch_cli(db_session, monkeypatch)
        with pytest.raises(SystemExit) as excinfo:
            main(["reset-password", "--email", "lockout@jobpilot-test.com"])
        assert excinfo.value.code == 1

    def test_refuses_test_without_disposable(self, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.cli.get_settings",
            lambda: get_settings().model_copy(update={"ENVIRONMENT": "test"}),
        )
        monkeypatch.delenv("JOBPILOT_DISPOSABLE_DATABASE_URL", raising=False)
        monkeypatch.delenv("JOBPILOT_DISPOSABLE_DATABASE_CONFIRM", raising=False)
        self.patch_cli(db_session, monkeypatch)
        with pytest.raises(SystemExit) as excinfo:
            main(["reset-password", "--email", "lockout@jobpilot-test.com"])
        assert excinfo.value.code == 1

    def test_refuses_test_with_unconfirmed_disposable(self, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.cli.get_settings",
            lambda: get_settings().model_copy(update={"ENVIRONMENT": "test"}),
        )
        monkeypatch.setenv(
            "JOBPILOT_DISPOSABLE_DATABASE_URL",
            "postgresql+psycopg://user:pass@127.0.0.1:5432/jobpilot_disposable_aaa",
        )
        monkeypatch.setenv("JOBPILOT_DISPOSABLE_DATABASE_CONFIRM", "something-else")
        self.patch_cli(db_session, monkeypatch)
        with pytest.raises(SystemExit) as excinfo:
            main(["reset-password", "--email", "lockout@jobpilot-test.com"])
        assert excinfo.value.code == 1

    def test_test_mode_accepts_confirmed_disposable_target(self, monkeypatch):
        monkeypatch.setattr(
            "app.cli.get_settings",
            lambda: get_settings().model_copy(update={"ENVIRONMENT": "test"}),
        )
        url = "postgresql+psycopg://user:pass@127.0.0.1:5432/jobpilot_disposable_aaa"
        monkeypatch.setenv("JOBPILOT_DISPOSABLE_DATABASE_URL", url)
        monkeypatch.setenv("JOBPILOT_DISPOSABLE_DATABASE_CONFIRM", "jobpilot_disposable_aaa")
        assert resolve_local_disposable_database() == url

    def test_test_mode_rejects_protected_database_name(self, monkeypatch):
        monkeypatch.setattr(
            "app.cli.get_settings",
            lambda: get_settings().model_copy(update={"ENVIRONMENT": "test"}),
        )
        monkeypatch.setenv(
            "JOBPILOT_DISPOSABLE_DATABASE_URL",
            "postgresql+psycopg://user:pass@127.0.0.1:5432/jobpilot_test",
        )
        monkeypatch.setenv("JOBPILOT_DISPOSABLE_DATABASE_CONFIRM", "jobpilot_test")
        with pytest.raises(SystemExit) as excinfo:
            resolve_local_disposable_database()
        assert excinfo.value.code == 1
