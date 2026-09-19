"""Application record origin: manual records stay manual, email-created records are email_confirmed."""
from datetime import datetime, timezone

from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import ApplicationRecord, SavedJob, User


TEST_PASSWORD = "origin-test-password"


def origin_users(db_session):
    first = User(email="origin-first@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add(first)
    db_session.commit()
    db_session.refresh(first)
    return first


def origin_client(client, db_session):
    def override():
        yield db_session

    client.app.dependency_overrides[get_db] = override
    yield client
    client.app.dependency_overrides.pop(get_db, None)


# Plain helpers (not pytest fixtures) so this module stays dependency-light.
def _users(db_session):
    return origin_users(db_session)


def test_manual_record_is_marked_manual(client, db_session):
    owner = _users(db_session)
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Example Systems",
                   location="Remote", description="Build APIs")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    created_response = None
    try:
        def override():
            yield db_session
        client.app.dependency_overrides[get_db] = override
        created_response = client.post(
            f"/api/jobs/{job.id}/applications",
            json={"submission_date": "2026-09-14T12:00:00Z", "method": "linkedin_manual", "status": "Applied"},
            headers=headers,
        )
    finally:
        client.app.dependency_overrides.pop(get_db, None)
    assert created_response.status_code == status.HTTP_201_CREATED, created_response.text
    assert created_response.json()["origin"] == "manual"


def test_backfilled_rows_default_to_manual(db_session):
    owner = _users(db_session)
    job = SavedJob(owner_id=owner.id, title="Legacy Role", company="Legacy Co",
                   description="Older record path")
    db_session.add(job)
    db_session.commit()
    legacy = ApplicationRecord(owner_id=owner.id, job_id=job.id,
                               submission_date=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
                               method="other", status="Applied")
    db_session.add(legacy)
    db_session.commit()
    db_session.refresh(legacy)
    assert legacy.origin == "manual"


def test_origin_is_rejected_on_write(client, db_session):
    owner = _users(db_session)
    job = SavedJob(owner_id=owner.id, title="Guarded Role", company="Guarded Co",
                   description="Client must not set origin")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    try:
        def override():
            yield db_session
        client.app.dependency_overrides[get_db] = override
        rejected = client.post(
            f"/api/jobs/{job.id}/applications",
            json={"submission_date": "2026-09-14T12:00:00Z", "method": "email",
                  "status": "Applied", "origin": "email_confirmed"},
            headers=headers,
        )
    finally:
        client.app.dependency_overrides.pop(get_db, None)
    assert rejected.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, rejected.text
