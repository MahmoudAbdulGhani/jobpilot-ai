"""Gated AI answer layer for Q&A: bounded citations, consent, no writes."""
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import DataUseConsent, SavedJob, User

TEST_PASSWORD = "qa-ai-test-password"


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_qa_ai_answer_bounded_and_read_only(client, db_session):
    owner = User(email="qa-ai-owner@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    other = User(email="qa-ai-other@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(other)
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   location="Remote", description="Build Python APIs with PostgreSQL.")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    db_session.add(DataUseConsent(owner_id=owner.id, key="ai_qa", allowed=True))
    db_session.commit()

    test_settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True,
        "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = api_client(client, db_session)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        before = db_session.scalar(select(func.count()).select_from(SavedJob).where(SavedJob.owner_id == owner.id))

        response = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python PostgreSQL"},
                              headers=auth(owner))
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["source"] == "ai"
        assert body["provider"] == "deterministic-test"
        assert body["model"] == "synthetic-v1"
        assert body["total"] == 1
        assert len(body["matches"]) == 1
        assert body["matches"][0]["id"] == str(job.id)
        assert len(body["citations"]) == 1 and body["citations"] == body["matches"]
        assert "verbatim excerpt" in body["answer"]

        after = db_session.scalar(select(func.count()).select_from(SavedJob).where(SavedJob.owner_id == owner.id))
        assert after == before, "the AI answer must not write anything"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_qa_ai_structured_fallbacks(client, db_session):
    owner = User(email="qa-ai-fallback@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.add(SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                            location="Remote", description="Build Python APIs."))
    db_session.commit()

    caller = api_client(client, db_session)
    try:
        ai_off = get_settings().model_copy(update={
            "JOBPILOT_AI_ENABLED": False, "JOBPILOT_AI_TEST_PROVIDER": True,
            "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB})
        client.app.dependency_overrides[get_settings] = lambda: ai_off
        disabled = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert disabled.status_code == status.HTTP_200_OK
        assert disabled.json()["source"] == "structured"
        assert "disabled" in disabled.json()["reason"]

        still_sha = get_settings().model_copy(update={
            "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
            "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB})
        client.app.dependency_overrides[get_settings] = lambda: still_sha
        no_consent = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert no_consent.status_code == status.HTTP_200_OK
        assert no_consent.json()["source"] == "structured"
        assert "Consent" in no_consent.json()["reason"]
        assert no_consent.json()["total"] == 1
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)