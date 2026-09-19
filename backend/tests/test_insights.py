"""Unified insights: owner isolation, redaction, evidence links."""
from datetime import datetime, timezone

from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import ApplicationRecord, SavedJob, User

TEST_PASSWORD = "insights-test-password"


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_insights_isolated_and_redacted(client, db_session):
    owner = User(email="insights-first@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    other = User(email="insights-second@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(other)
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description="Build APIs")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    db_session.add(ApplicationRecord(
        owner_id=owner.id, job_id=job.id,
        submission_date=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        method="linkedin_manual", status="Applied", origin="manual",
        notes="Private note that must not leak in full"))
    db_session.commit()

    caller = api_client(client, db_session)
    try:
        body = caller.get("/api/insights", headers=auth(owner))
        assert body.status_code == status.HTTP_200_OK, body.text
        payload = body.json()
        assert payload["application_counts"] == {"Applied": 1}
        assert payload["applications"][0]["origin"] == "manual"
        assert payload["applications"][0]["link"]["href"] == f"/jobs/{job.id}"
        assert "Private note" not in body.text, "notes must not be embedded"
        assert payload["reminder_counts"] == {"overdue": 0, "upcoming": 0}

        foreign = caller.get("/api/insights", headers=auth(other))
        assert foreign.json()["application_counts"] == {}, "owners see only their data"
        assert foreign.json()["applications"] == []
    finally:
        client.app.dependency_overrides.pop(get_db, None)
