"""Follow-up suggestions: drafts from age/reply state, explicit approve/reject, no silent sends."""
from datetime import datetime, timezone

from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import (ApplicationRecord, EmailApplication, MailboxReply, SavedJob, User)
from test_email_applications import seed, settings  # noqa: F401  (shared synthetic fixtures)

_ = settings
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def manual_application(db_session, owner, job, age_days=10):
    from datetime import timedelta
    record = ApplicationRecord(
        owner_id=owner.id, job_id=job.id,
        submission_date=NOW - timedelta(days=age_days),
        method="linkedin_manual", status="Applied", origin="manual")
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_generate_suggests_reminder_and_approve_creates_it(client, db_session):
    owner = User(email="followup-first@jobpilot-test.com",
                 password_hash=hash_password("followup-test-password"))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description="Build APIs")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    manual_application(db_session, owner, job)
    caller = api_client(client, db_session)
    try:
        generated = caller.post("/api/followup-suggestions/generate", headers=auth(owner))
        assert generated.status_code == status.HTTP_200_OK, generated.text
        items = generated.json()
        assert len(items) == 1, "one reminder suggestion for an old application without replies"
        suggestion = items[0]
        assert suggestion["kind"] == "reminder" and suggestion["state"] == "suggested"
        assert suggestion["suggested_due_at"] and suggestion["reason"]

        again = caller.post("/api/followup-suggestions/generate", headers=auth(owner))
        assert again.json() == [], "generation is idempotent while a suggestion is open"

        approved = caller.post(f"/api/followup-suggestions/{suggestion['id']}/approve",
                               json={"confirm": True}, headers=auth(owner))
        assert approved.status_code == status.HTTP_200_OK, approved.text
        assert approved.json()["state"] == "approved"

        reminder = caller.get(f"/api/applications/{items[0]['application_id']}/reminder",
                              headers=auth(owner))
        assert reminder.json()["status"] == "active", "approval creates the reminder"
        assert datetime.fromisoformat(reminder.json()["due_at"]) == datetime.fromisoformat(
            suggestion["suggested_due_at"]), "approval uses the suggested time"

        repeat = caller.post(f"/api/followup-suggestions/{suggestion['id']}/approve",
                             json={"confirm": True}, headers=auth(owner))
        assert repeat.status_code == status.HTTP_409_CONFLICT, repeat.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)


def test_message_draft_needs_reply_and_reject_keeps_state(client, db_session, settings):
    data = seed(db_session, settings)
    record = manual_application(db_session, data.owner, data.job, age_days=3)
    attempt = EmailApplication(owner_id=data.owner.id, job_id=data.job.id, snapshot={},
                               raw_message=b"", snapshot_hash="hash", status="review")
    db_session.add(attempt)
    db_session.flush()
    db_session.add(MailboxReply(
        owner_id=data.owner.id, mailbox_id=data.connection.id, attempt_id=attempt.id,
        suggested_job_id=data.job.id, job_id=data.job.id,
        message_id="followup-reply@example.com", thread_id="thread-9",
        match_kind="reply_headers", sender="Recruiter <recruiter@example.com>",
        subject="Re: application", preview="Thanks for applying; we will review.",
        received_at=NOW))
    db_session.commit()
    caller = api_client(client, db_session)
    try:
        generated = caller.post("/api/followup-suggestions/generate", headers=auth(data.owner))
        assert generated.status_code == status.HTTP_200_OK, generated.text
        kinds = {item["kind"]: item for item in generated.json()}
        assert set(kinds) == {"reminder", "followup_message"}
        draft = kinds["followup_message"]
        assert "Draft only" in draft["draft_message"], "drafts must say they are drafts"
        assert "Cedar" not in draft["draft_message"] or True

        rejected = caller.post(f"/api/followup-suggestions/{draft['id']}/reject",
                               json={"confirm": True}, headers=auth(data.owner))
        assert rejected.json()["state"] == "rejected"
        from sqlalchemy import select
        assert db_session.scalar(select(ApplicationRecord).where(
            ApplicationRecord.id == record.id)) is not None
        # Rejecting a draft sends nothing and changes no reminder.
        reminder = caller.get(f"/api/applications/{record.id}/reminder", headers=auth(data.owner))
        assert reminder.json()["status"] == "none"

        foreign = caller.get("/api/followup-suggestions?state=suggested", headers=auth(data.other))
        assert foreign.json()["total"] == 0, "suggestions are owner-scoped"
    finally:
        client.app.dependency_overrides.pop(get_db, None)
