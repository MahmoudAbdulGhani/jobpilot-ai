"""Read-only Q&A: owner scope, field allowlists, row limits, citations, no writes."""
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import func, select

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import ApplicationRecord, SavedJob, User

TEST_PASSWORD = "qa-test-password"


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_qa_answers_with_citations_and_leaks_nothing(client, db_session):
    owner = User(email="qa-first@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    other = User(email="qa-second@jobpilot-test.com", password_hash=hash_password(TEST_PASSWORD))
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(other)
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   location="Remote", description="Build Python APIs with PostgreSQL.")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    db_session.add(ApplicationRecord(
        owner_id=owner.id, job_id=job.id,
        submission_date=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        method="linkedin_manual", status="Applied", origin="manual"))
    db_session.commit()
    before = db_session.scalar(select(func.count()).select_from(
        SavedJob).where(SavedJob.owner_id == owner.id))

    caller = api_client(client, db_session)
    try:
        answer = caller.get("/api/qa/ask", params={"entity": "jobs", "q": "Python PostgreSQL"},
                            headers=auth(owner))
        assert answer.status_code == status.HTTP_200_OK, answer.text
        body = answer.json()
        assert body["total"] == 1 and len(body["matches"]) == 1
        match = body["matches"][0]
        assert match["entity"] == "jobs" and match["id"] == str(job.id)
        assert match["field"] in {"title", "company", "location", "description", "notes"}
        assert "Python" in match["excerpt"] and match["href"] == f"/jobs/{job.id}"

        apps = caller.get("/api/qa/ask", params={"entity": "applications", "q": "Applied"},
                          headers=auth(owner))
        assert apps.json()["total"] == 1

        foreign = caller.get("/api/qa/ask", params={"entity": "jobs", "q": "Python"},
                             headers=auth(other))
        assert foreign.json()["total"] == 0, "questions span only the asker's data"

        # No field outside the allowlist is searchable or returned.
        assert caller.get("/api/qa/ask", params={"entity": "jobs", "q": "qa-first"},
                          headers=auth(owner)).json()["total"] == 0
        scoped = caller.get("/api/qa/ask", params={"entity": "profile", "q": "zzz-no-such-term"},
                            headers=auth(owner))
        assert scoped.json()["matches"] == []

        bad_scope = caller.get("/api/qa/ask", params={"entity": "secrets", "q": "Python"},
                               headers=auth(owner))
        assert bad_scope.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, bad_scope.text
        empty = caller.get("/api/qa/ask", params={"entity": "jobs", "q": "the and"},
                           headers=auth(owner))
        assert empty.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, empty.text
        over = caller.get("/api/qa/ask", params={"entity": "jobs", "q": "Python", "limit": 99},
                          headers=auth(owner))
        assert over.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, over.text

        after = db_session.scalar(select(func.count()).select_from(
            SavedJob).where(SavedJob.owner_id == owner.id))
        assert after == before, "asking must not write anything"
    finally:
        client.app.dependency_overrides.pop(get_db, None)
