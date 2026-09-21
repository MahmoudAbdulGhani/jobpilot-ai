"""Gated AI answer layer for Q&A: bounded citations, consent, no writes."""
from datetime import datetime, timezone

import pytest
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
        assert body["answer"] == body["citations"][0]["excerpt"]

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
            "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
            "JOBPILOT_QA_STRUCTURED_FALLBACK": True})
        client.app.dependency_overrides[get_settings] = lambda: ai_off
        disabled = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert disabled.status_code == status.HTTP_200_OK
        assert disabled.json()["source"] == "structured"
        assert "unavailable" in disabled.json()["reason"]

        still_sha = get_settings().model_copy(update={
            "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
            "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB})
        client.app.dependency_overrides[get_settings] = lambda: still_sha
        no_consent = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert no_consent.status_code == status.HTTP_403_FORBIDDEN
        assert "consent" in no_consent.json()["detail"].casefold()
        assert caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner)).status_code == status.HTTP_403_FORBIDDEN
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_qa_ai_without_consent_never_calls_provider(client, db_session, monkeypatch):
    from app.services import qa_service
    owner = User(email="qa-ai-denied@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.add(SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                            location="Remote", description="Build Python APIs."))
    db_session.commit()

    def forbidden(*a): pytest.fail("QA provider must not be called without consent")
    monkeypatch.setattr(qa_service, "_provider_for", forbidden)
    still_sha = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB})
    caller = api_client(client, db_session)
    try:
        client.app.dependency_overrides[get_settings] = lambda: still_sha
        denied = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert denied.status_code == status.HTTP_403_FORBIDDEN, denied.text
        assert "consent" in denied.json()["detail"].casefold()
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_qa_ai_revoked_consent_never_calls_provider_again(client, db_session, monkeypatch):
    from app.services import qa_service, privacy_service
    from app.services.ai_provider import DeterministicTestProvider
    owner = User(email="qa-ai-revoked@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.add(SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                            location="Remote", description="Build Python APIs."))
    db_session.add(DataUseConsent(owner_id=owner.id, key="ai_qa", allowed=True))
    db_session.commit()

    calls = []
    class Recorder:
        name = "deterministic-test"
        model = "synthetic-v1"
        def answer(self, question, citations):
            calls.append(question)
            return DeterministicTestProvider().answer(question, citations)
    monkeypatch.setattr(qa_service, "_provider_for", lambda settings: Recorder())
    still_sha = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB})
    caller = api_client(client, db_session)
    try:
        client.app.dependency_overrides[get_settings] = lambda: still_sha
        first = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert first.status_code == status.HTTP_200_OK and first.json()["source"] == "ai"
        assert len(calls) == 1
        privacy_service.set_consent(db_session, owner.id, "ai_qa", False)  # Revoked mid-usage.
        second = caller.get("/api/qa/answer", params={"entity": "jobs", "q": "Python"}, headers=auth(owner))
        assert second.status_code == status.HTTP_403_FORBIDDEN
        assert second.json()["detail"].casefold().count("consent")
        assert len(calls) == 1, "no provider call after revocation"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("failure", [None, "foreign", "number", "claim", "irrelevant", "timeout"])
def test_production_qa_uses_ai_and_rejects_unsafe_answers(db_session, monkeypatch, failure):
    import uuid
    from app.services import qa_service
    from app.services.ai_provider import ProviderFailure
    from app.schemas.qa import ProviderQaOutput
    from fastapi import HTTPException
    owner = User(email=f"qa-prod-{uuid.uuid4()}@example.test", password_hash="unused")
    other = User(email=f"qa-prod-{uuid.uuid4()}@example.test", password_hash="unused")
    db_session.add_all([owner, other]); db_session.commit()
    db_session.add_all([
        SavedJob(owner_id=owner.id, title="Python", company="Owner", description="Python services"),
        SavedJob(owner_id=other.id, title="Python private", company="Private"),
        DataUseConsent(owner_id=owner.id, key="ai_qa", allowed=True)])
    db_session.commit()
    calls = []
    class Provider:
        name, model = "mock", "offline"
        def answer(self, question, citations):
            calls.append(citations)
            assert len(citations) == 1 and citations[0]["excerpt"] == "Python"
            citation = dict(citations[0])
            if failure == "timeout":
                raise ProviderFailure("private provider error must not escape")
            if failure == "foreign":
                citation["id"] = str(uuid.uuid4())
            answer = {"number": "Python 999", "claim": "Python expert", "irrelevant": "French"}.get(failure, "Python")
            return ProviderQaOutput(answer=answer, citations=[citation])
    monkeypatch.setattr(qa_service, "_provider_for", lambda settings: Provider())
    settings = get_settings().model_copy(update={"ENVIRONMENT": "production", "JOBPILOT_AI_ENABLED": True})
    if failure:
        with pytest.raises(HTTPException) as error:
            qa_service.answer(db_session, owner.id, "jobs", "Python", 10, settings)
        assert error.value.status_code == 503
        assert "private provider" not in error.value.detail
    else:
        result = qa_service.answer(db_session, owner.id, "jobs", "Python", 10, settings)
        assert result.source == "ai" and result.answer == "Python"
    assert len(calls) == 1
