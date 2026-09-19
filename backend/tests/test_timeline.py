"""Application timeline: read-only, deterministic, owner-scoped narrative."""
import uuid
from datetime import datetime, timezone

from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import SavedJob, User
from app.models.application_tracking import ApplicationRecord, ApplicationStatusEvent
from app.models.email_application import EmailApplication
from app.models.followup_suggestion import FollowupSuggestion
from app.models.mailbox import MailboxConnection
from app.models.mailbox_reply import MailboxReply
from app.schemas.application_tracking import ApplicationCreate
from app.services import application_tracking_service

TEST_PASSWORD = "timeline-test-password"
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def make_user(db_session, email):
    user = User(email=email, password_hash=hash_password(TEST_PASSWORD))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def seed(db_session, owner, job):
    payload = ApplicationCreate(job_id=job.id, submission_date=NOW,
                                method="email", notes=None, status="Applied")
    app = application_tracking_service.create_application(
        db_session, owner_id=owner.id, payload=payload)
    application_tracking_service.record_status_event(db_session, app.id, "Interview")

    mailbox = MailboxConnection(owner_id=owner.id, provider="gmail",
                                subject="ada@example.com", email="ada@example.com")
    db_session.add(mailbox)
    db_session.flush()
    email_app = EmailApplication(owner_id=owner.id, job_id=job.id, application_id=app.id,
                                 snapshot={}, raw_message=b"raw", snapshot_hash="a" * 64,
                                 approved_at=datetime(2026, 9, 15, 9, tzinfo=timezone.utc),
                                 status="sent", outcome="delivered")
    db_session.add(email_app)
    db_session.flush()
    reply = MailboxReply(owner_id=owner.id, mailbox_id=mailbox.id, attempt_id=email_app.id,
                         suggested_job_id=job.id, job_id=job.id,
                         message_id="msg-1", thread_id="thr-1",
                         match_kind="job_title", sender="recruiter@example.com",
                         subject="Interview invitation", preview="Let's schedule a call",
                         received_at=datetime(2026, 9, 16, 10, tzinfo=timezone.utc))
    db_session.add(reply)
    suggestion = FollowupSuggestion(owner_id=owner.id, application_id=app.id, kind="reminder",
                                    suggested_due_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
                                    draft_message="", reason="No reply after one week",
                                    state="suggested",
                                    decided_at=datetime(2026, 9, 17, 9, tzinfo=timezone.utc))
    db_session.add(suggestion)
    db_session.commit()
    db_session.refresh(app)
    return app


def test_timeline_read_only_narrative(client, db_session):
    owner = make_user(db_session, "timeline-owner@jobpilot-test.com")
    other = make_user(db_session, "timeline-other@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   location="Remote", description="FastAPI and PostgreSQL.")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    app = seed(db_session, owner, job)

    api_client(client, db_session)
    response = client.get(f"/api/jobs/{job.id}/applications/{app.id}/timeline", headers=auth(owner))
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["application_id"] == str(app.id)
    assert body["job_id"] == str(job.id)
    assert "Backend Engineer" in body["narrative"]
    assert body["total"] == len(body["entries"]) == 6

    kinds = [entry["kind"] for entry in body["entries"]]
    assert kinds == ["submitted", "email", "reply", "followup", "status", "status"], kinds
    times = [entry["at"] for entry in body["entries"]]
    assert times == sorted(times), "timeline is chronological"

    submitted = body["entries"][0]
    assert submitted["kind"] == "submitted"
    assert submitted["title"].startswith("Application recorded via email")
    assert all(line in submitted["evidence"] for line in ["Origin: manual", "Method: email"])

    reply_entry = next(entry for entry in body["entries"] if entry["kind"] == "reply")
    assert reply_entry["title"] == "Reply received: Interview invitation"
    assert reply_entry["detail"] == "Let's schedule a call"
    email_entry = next(entry for entry in body["entries"] if entry["kind"] == "email")
    assert email_entry["title"] == "Email application sent"
    assert email_entry["detail"] == "delivered"
    followup_entry = next(entry for entry in body["entries"] if entry["kind"] == "followup")
    assert followup_entry["title"] == "Follow-up suggestion (reminder) suggested"


def test_timeline_owner_isolation(client, db_session):
    owner = make_user(db_session, "timeline-iso-owner@jobpilot-test.com")
    other = make_user(db_session, "timeline-iso-other@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Data Engineer", company="Lumen",
                   location="Remote", description="dbt and SQL.")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    app = seed(db_session, owner, job)

    api_client(client, db_session)
    foreign = client.get(f"/api/jobs/{job.id}/applications/{app.id}/timeline", headers=auth(other))
    assert foreign.status_code == status.HTTP_404_NOT_FOUND
    missing = client.get(f"/api/jobs/{job.id}/applications/{uuid.uuid4()}/timeline",
                         headers=auth(owner))
    assert missing.status_code == status.HTTP_404_NOT_FOUND