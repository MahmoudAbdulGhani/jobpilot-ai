import contextlib
import getpass

import pytest
from sqlalchemy import func, select

from app.cli import MIN_PASSWORD_LENGTH, main, prompt_credentials
from app.models import User

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
