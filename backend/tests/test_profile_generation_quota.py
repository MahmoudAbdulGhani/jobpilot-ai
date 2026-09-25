"""Profile quota decisions without provider or database side effects."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import ai_usage, profile_generation_quota as quota


class SessionStub:
    def __init__(self):
        self.rows = []

    def scalar(self, query):
        return uuid.UUID("00000000-0000-0000-0000-000000000001")

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        pass


@pytest.mark.parametrize("admin,seen,used,expected_kind,bypass", [
    (False, False, 2, "initial", True),
    (False, True, 0, "refresh", False),
    (False, True, 1, "refresh", False),
    (True, True, 900, "admin", False),
])
def test_reservation_classification(monkeypatch, admin, seen, used, expected_kind, bypass):
    owner = uuid.uuid4()
    token = uuid.uuid4()
    at = datetime(2026, 9, 25, tzinfo=timezone.utc)
    db = SessionStub()
    calls = []
    monkeypatch.setattr(quota, "_facts", lambda *args: (admin, seen, used, at, at, at))
    monkeypatch.setattr(ai_usage, "reserve", lambda *args, **kwargs: calls.append(kwargs) or token)
    assert quota.reserve(db, owner, "a" * 64, object()) == token
    assert calls == ([{"feature": "profile", "bypass_monthly_limits": True}] if bypass else [{"feature": "profile"}])
    assert len(db.rows) == 1
    assert db.rows[0].kind == expected_kind
    assert db.rows[0].source_hash == "a" * 64


def test_two_refreshes_rejects_without_reserving(monkeypatch):
    at = datetime(2026, 9, 25, tzinfo=timezone.utc)
    db = SessionStub()
    monkeypatch.setattr(quota, "_facts", lambda *args: (False, True, 2, at, at, at))
    monkeypatch.setattr(ai_usage, "reserve", lambda *args, **kwargs: pytest.fail("unexpected provider reservation"))
    with pytest.raises(ai_usage.AIUsageError) as error:
        quota.reserve(db, uuid.uuid4(), "b" * 64, object())
    assert error.value.status_code == 429
    assert not db.rows


def test_eligibility_explains_new_cv_after_refresh_limit(monkeypatch):
    from app.services import entitlements
    from app.services import privacy_service, profile_suggestion_service

    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    settings = SimpleNamespace(JOBPILOT_AI_MAX_INPUT_CHARS=1000)
    extraction = SimpleNamespace(draft_text="Synthetic CV", status="succeeded", reviewed_at=at)
    monkeypatch.setattr(quota, "_facts", lambda *args: (False, False, 2, at, at, at))
    monkeypatch.setattr(privacy_service, "is_consented", lambda *args: True)
    monkeypatch.setattr(profile_suggestion_service, "provider_configuration", lambda *args: ("test", "test", None))
    monkeypatch.setattr(entitlements, "policy", lambda *args: ("free", 0, {"profile": 1}, None))
    monkeypatch.setattr(entitlements, "consumption", lambda *args: (20, {"profile": 20}))
    monkeypatch.setattr(entitlements, "period", lambda *args: (at, at))
    monkeypatch.setattr(entitlements, "now", lambda: at)
    result = quota.eligibility(None, uuid.uuid4(), extraction, settings)
    assert result["allowed"] and result["kind"] == "initial"
    assert result["remaining_refreshes"] == 0


def test_eligibility_blocks_disabled_feature_even_for_new_cv(monkeypatch):
    from app.services import entitlements
    from app.services import privacy_service, profile_suggestion_service

    at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    settings = SimpleNamespace(JOBPILOT_AI_MAX_INPUT_CHARS=1000)
    extraction = SimpleNamespace(draft_text="Different CV", status="succeeded", reviewed_at=at)
    monkeypatch.setattr(quota, "_facts", lambda *args: (False, False, 0, at, at, at))
    monkeypatch.setattr(privacy_service, "is_consented", lambda *args: True)
    monkeypatch.setattr(profile_suggestion_service, "provider_configuration", lambda *args: ("test", "test", None))
    monkeypatch.setattr(entitlements, "policy", lambda *args: ("free", 0, {"profile": 0}, None))
    monkeypatch.setattr(entitlements, "consumption", lambda *args: (0, {}))
    monkeypatch.setattr(entitlements, "period", lambda *args: (at, at))
    monkeypatch.setattr(entitlements, "now", lambda: at)
    result = quota.eligibility(None, uuid.uuid4(), extraction, settings)
    assert not result["allowed"]
    assert result["kind"] == "initial"
