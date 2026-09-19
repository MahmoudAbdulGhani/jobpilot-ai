"""Reply classification: advisory categories, explicit confirmation, no auto-status."""
import uuid
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import select

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import ApplicationRecord, EmailApplication, MailboxReply, User
from app.services import reply_classification_service as service
from test_email_applications import seed, settings  # noqa: F401  (shared synthetic fixtures)

_ = settings


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def reply(db_session, data, subject, preview, job=None):
    attempt = EmailApplication(owner_id=data.owner.id, job_id=data.job.id, snapshot={},
                               raw_message=b"", snapshot_hash="hash", status="review")
    db_session.add(attempt)
    db_session.flush()
    row = MailboxReply(owner_id=data.owner.id, mailbox_id=data.connection.id,
                       attempt_id=attempt.id, suggested_job_id=data.job.id,
                       job_id=job.id if job else None,
                       message_id=f"{uuid.uuid4()}@example.com", thread_id="thread-1",
                       match_kind="reply_headers", sender="Recruiter <recruiter@example.com>",
                       subject=subject, preview=preview,
                       received_at=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_classifier_matrix():
    interview = service.classify_text("Re: application", "We would like to invite you to an interview next week.")
    assert interview["category"] == "interview" and interview["suggested_status"] == "Interview"
    assert interview["confidence"] >= 50 and interview["evidence_excerpt"]
    rejection = service.classify_text("Update", "Unfortunately we decided to move forward with other candidates.")
    assert rejection["category"] == "rejection" and rejection["suggested_status"] == "Rejected"
    offer = service.classify_text("Offer", "We are pleased to offer you the role. Offer letter attached.")
    assert offer["category"] == "offer" and offer["suggested_status"] == "Offer"
    request = service.classify_text("Quick question", "Could you share your availability for a call?")
    assert request["category"] == "information_request" and request["suggested_status"] is None
    other = service.classify_text("Hello", "Thanks for getting in touch, wishing you well.")
    assert other["category"] == "other" and other["confidence"] <= 40 and other["uncertainty"]
    competing = service.classify_text("Next", "We invite you to an interview. Unfortunately the start date moved.")
    assert "Competing signals" in competing["uncertainty"]


def test_classify_never_changes_status_and_confirm_is_explicit(client, db_session, settings):
    data = seed(db_session, settings)
    target = reply(db_session, data, "Interview invitation",
                   "We would like to invite you to an interview next week.", job=data.job)
    caller = api_client(client, db_session)
    try:
        created = caller.post(f"/api/replies/{target.id}/classification", headers=auth(data.owner))
        assert created.status_code == status.HTTP_200_OK, created.text
        body = created.json()
        assert body["category"] == "interview"
        assert body["status_applied"] is False
        assert db_session.scalar(select(ApplicationRecord).where(
            ApplicationRecord.job_id == data.job.id)) is None, "classification must not create status"

        fetched = caller.get(f"/api/replies/{target.id}/classification", headers=auth(data.owner))
        assert fetched.json()["id"] == body["id"]

        # No application record yet: confirmation must refuse, not invent one.
        refused = caller.post(f"/api/replies/{target.id}/classification/confirm",
                              json={"confirm": True, "status": "Interview"}, headers=auth(data.owner))
        assert refused.status_code == status.HTTP_409_CONFLICT, refused.text

        manual = ApplicationRecord(owner_id=data.owner.id, job_id=data.job.id,
                                   submission_date=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
                                   method="linkedin_manual", status="Applied", origin="manual")
        db_session.add(manual)
        db_session.commit()

        sloppy = caller.post(f"/api/replies/{target.id}/classification/confirm",
                             json={"status": "Interview"}, headers=auth(data.owner))
        assert sloppy.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, sloppy.text

        confirmed = caller.post(f"/api/replies/{target.id}/classification/confirm",
                                json={"confirm": True, "status": "Interview"}, headers=auth(data.owner))
        assert confirmed.status_code == status.HTTP_200_OK, confirmed.text
        assert confirmed.json()["status_applied"] is True
        assert confirmed.json()["applied_status"] == "Interview"
        db_session.refresh(manual)
        assert manual.status == "Interview"

        foreign = caller.post(f"/api/replies/{target.id}/classification", headers=auth(data.other))
        assert foreign.status_code == status.HTTP_404_NOT_FOUND, foreign.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)


def test_confirm_requires_prior_classification(client, db_session, settings):
    data = seed(db_session, settings)
    target = reply(db_session, data, "Hello", "Wishing you well.", job=data.job)
    manual = ApplicationRecord(owner_id=data.owner.id, job_id=data.job.id,
                               submission_date=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
                               method="other", status="Applied", origin="manual")
    db_session.add(manual)
    db_session.commit()
    caller = api_client(client, db_session)
    try:
        refused = caller.post(f"/api/replies/{target.id}/classification/confirm",
                              json={"confirm": True, "status": "Rejected"}, headers=auth(data.owner))
        assert refused.status_code == status.HTTP_409_CONFLICT, refused.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)
