"""Shared test helper for granting/revoking optional-consent toggles.

Fail-closed contract: every AI dispatch path calls
``privacy_service.require_consent`` before the provider is reached. Tests that
are about something else (limits, quotas, providers, entitlements, routing)
must still grant the relevant consent so the code path under test is reached;
denial is asserted where the test's job is exactly "denied => 403".
"""

from sqlalchemy.orm import Session

from app.services import privacy_service

CONSENT_KEYS = {
    "ai_qa",
    "ai_interview",
    "ai_voice",
    "ai_job_fit",
    "ai_profile_suggestions",
    "ai_application_packs",
}


def grant_consent(db: Session, owner_id, key: str, allowed: bool = True) -> None:
    """Upsert a consent toggle. ``allowed=False`` revokes an existing grant."""
    assert key in CONSENT_KEYS, f"unknown optional consent key: {key}"
    privacy_service.set_consent(db, owner_id, key, allowed)