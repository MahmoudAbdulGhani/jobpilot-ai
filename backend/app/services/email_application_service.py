import base64
import hashlib
import json
import uuid
from datetime import timedelta
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import ApplicationPack, ApplicationPackVersion, ApplicationRecord, ApplicationStatusEvent, EmailApplication, SavedJob
from app.services import mailbox_service as mailbox
from app.services import pack_export
from app.services.application_pack_service import PackError
from app.services.mailbox_provider import MailboxError, SCOPES, provider_for, seal, unseal
from app.services.email_sender import sender_for

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_MESSAGE_BYTES = 15 * 1024 * 1024


def digest(snapshot, raw):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode() + b"\0" + raw).hexdigest()


def owned_job(db, owner, job_id):
    job = db.scalar(select(SavedJob).where(SavedJob.id == job_id, SavedJob.owner_id == owner).with_for_update())
    if not job:
        raise PackError(404, "Job not found")
    return job


def owned(db, owner, job_id, attempt_id):
    row = db.scalar(select(EmailApplication).where(EmailApplication.id == attempt_id,
        EmailApplication.owner_id == owner, EmailApplication.job_id == job_id).execution_options(populate_existing=True))
    if not row:
        raise PackError(404, "Email application not found")
    return row


def approved_version(db, owner, job_id, pack_id, number):
    pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == pack_id,
        ApplicationPack.owner_id == owner, ApplicationPack.job_id == job_id).with_for_update())
    if not pack:
        raise PackError(404, "Pack not found for this job")
    version = db.scalar(select(ApplicationPackVersion).where(ApplicationPackVersion.pack_id == pack.id,
        ApplicationPackVersion.number == number).with_for_update().execution_options(populate_existing=True))
    if pack.status != "ready" or not version or not version.approved_at:
        raise PackError(409, "Select an approved pack version")
    return version


def validate_mailbox(row, provider):
    if row.provider != provider.name or row.status != "connected" or not row.credentials or "send" not in row.capabilities:
        raise PackError(409, "Reconnect a mailbox with sending permission in Settings")


def create_review(db, owner, job_id, body, settings):
    mailbox.owner_lock(db, owner)
    owned_job(db, owner, job_id)
    if db.scalar(select(ApplicationRecord.id).where(ApplicationRecord.owner_id == owner, ApplicationRecord.job_id == job_id)):
        raise PackError(409, "This job already has an application record; sending again is blocked")
    previous = db.scalar(select(EmailApplication).where(EmailApplication.owner_id == owner,
        EmailApplication.job_id == job_id, EmailApplication.status.in_(["review", "queued", "sending", "sent", "unknown", "simulated"])))
    if previous and previous.status != "review":
        raise PackError(409, "An email submission already exists. Check its outcome; do not resend")
    version = approved_version(db, owner, job_id, body.pack_id, body.pack_version)
    connection = mailbox.owned(db, owner, body.mailbox_id)
    provider = provider_for(settings)
    validate_mailbox(connection, provider)
    attachments = []
    for name, document in (("cv", version.cv), ("cover_letter", version.cover_letter)):
        raw = pack_export.render_document({"blocks": [{"kind": b["kind"], "text": b["text"]} for b in document["blocks"]]}, "pdf")
        if not raw or len(raw) > MAX_ATTACHMENT_BYTES:
            raise PackError(422, "An attachment exceeds the 5 MiB limit")
        attachments.append({"name": f"{name}-v{version.number}.pdf", "content_type": "application/pdf",
            "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "data": base64.b64encode(raw).decode()})
    attempt_id = uuid.uuid4()
    snapshot = {"mailbox_id": str(connection.id), "sender": connection.email, "provider": connection.provider,
        "recipient": str(body.recipient), "recipient_source": body.recipient_source,
        "subject": body.subject, "body": body.body, "pack_id": str(body.pack_id), "pack_version": version.number,
        "pack_approved_at": version.approved_at.isoformat(), "cv": version.cv, "cover_letter": version.cover_letter,
        "attachments": attachments}
    message = EmailMessage(policy=SMTP)
    message["From"], message["To"], message["Subject"] = connection.email, str(body.recipient), body.subject
    message["Date"] = format_datetime(mailbox.now())
    message["Message-ID"] = f"<{attempt_id}@jobpilot.invalid>"
    message.set_content(body.body)
    for attachment in attachments:
        message.add_attachment(base64.b64decode(attachment["data"]), maintype="application", subtype="pdf", filename=attachment["name"])
    raw_message = message.as_bytes()
    if len(raw_message) > MAX_MESSAGE_BYTES:
        raise PackError(422, "Message exceeds the 15 MiB limit")
    if previous:
        previous.status = "cancelled"
        db.flush()  # Release the unique active-job slot before insertion.
    row = EmailApplication(id=attempt_id, owner_id=owner, job_id=job_id, snapshot=snapshot,
        raw_message=raw_message, snapshot_hash=digest(snapshot, raw_message), status="review")
    db.add(row)
    db.commit()
    return row


def public(row):
    snap = row.snapshot
    status, outcome = row.status, row.outcome
    if status == "sending" and row.dispatch_at and row.dispatch_at < mailbox.now() - timedelta(minutes=2):
        status, outcome = "unknown", "dispatch_interrupted_or_unconfirmed"
    return {"id": str(row.id), "status": status, "outcome": outcome, "snapshot_hash": row.snapshot_hash,
        "approved_at": row.approved_at, "created_at": row.created_at,
        "provider_message_id": row.provider_message_id, "provider_thread_id": row.provider_thread_id,
        "provider_status": row.provider_status, "application_id": str(row.application_id) if row.application_id else None,
        "snapshot": {k: v for k, v in snap.items() if k not in ("cv", "cover_letter", "attachments")},
        "attachments": [{k: v for k, v in a.items() if k != "data"} for a in snap["attachments"]]}


def cancel(db, owner, job_id, attempt_id):
    mailbox.owner_lock(db, owner)
    row = owned(db, owner, job_id, attempt_id)
    if row.status != "review":
        raise PackError(409, "Only an unsent review can be cancelled")
    row.status = "cancelled"
    db.commit()
    return row


def send(db, owner, job_id, attempt_id, approval, settings):
    mailbox.owner_lock(db, owner)
    row = owned(db, owner, job_id, attempt_id)
    if approval.snapshot_hash != row.snapshot_hash or digest(row.snapshot, row.raw_message) != row.snapshot_hash:
        raise PackError(409, "Review changed; prepare and approve a new snapshot")
    if row.status not in ("review", "queued"):
        # Retrying the HTTP request is a status lookup, never another dispatch.
        return row
    if row.status == "review":
        row.approved_at, row.approved_hash, row.status = mailbox.now(), row.snapshot_hash, "queued"
        db.commit()  # Approval survives a process interruption; never inferred from UI state.
    mailbox.owner_lock(db, owner)
    row = owned(db, owner, job_id, attempt_id)
    if row.status != "queued":
        return row
    row.status, row.dispatch_at = "sending", mailbox.now()
    db.commit()  # One durable claim. A crash beyond this point must never retry dispatch.
    mailbox.owner_lock(db, owner)
    row = owned(db, owner, job_id, attempt_id)
    snap = row.snapshot
    try:
        owned_job(db, owner, job_id)
        version = approved_version(db, owner, job_id, uuid.UUID(snap["pack_id"]), snap["pack_version"])
        if (row.approved_hash != row.snapshot_hash or version.cv != snap["cv"] or version.cover_letter != snap["cover_letter"]
                or version.approved_at.isoformat() != snap["pack_approved_at"]):
            raise PackError(409, "approval_invalid")
        if db.scalar(select(ApplicationRecord.id).where(ApplicationRecord.owner_id == owner, ApplicationRecord.job_id == job_id)):
            raise PackError(409, "application_already_recorded")
        connection = mailbox.owned(db, owner, uuid.UUID(snap["mailbox_id"]))
        provider = provider_for(settings)
        validate_mailbox(connection, provider)
        if connection.email != snap["sender"] or connection.provider != snap["provider"]:
            raise PackError(409, "mailbox_identity_changed")
        tokens = unseal(settings, mailbox.context(connection), connection.credentials)
        refreshed = provider.refresh(tokens["refresh_token"])
        connection.credentials = seal(settings, mailbox.context(connection), {**refreshed.model_dump(),
            "refresh_token": refreshed.refresh_token or tokens["refresh_token"]})
        connection.expires_at = mailbox.now() + timedelta(seconds=refreshed.expires_in)
        connection.capabilities = [c for c in connection.capabilities if SCOPES[c] in refreshed.scope.split()]
        if "send" not in connection.capabilities:
            raise PackError(409, "sending_permission_missing")
        sender = sender_for(settings)
    except (MailboxError, PackError) as error:
        reason = error.code if isinstance(error, MailboxError) else {
            "Reconnect a mailbox with sending permission in Settings": "sending_permission_unavailable",
            "Select an approved pack version": "pack_unapproved",
            "Pack not found for this job": "pack_unavailable",
            "approval_invalid": "approval_invalid",
            "application_already_recorded": "application_already_recorded",
            "mailbox_identity_changed": "mailbox_identity_changed",
            "sending_permission_missing": "sending_permission_missing",
        }.get(error.message, "rejected")
        row.status, row.outcome = "failed", f"preflight_{reason}_no_dispatch"
        if isinstance(error, MailboxError) and error.code in ("reconnect_required", "credential_unavailable") and 'connection' in locals():
            connection.status, connection.credentials, connection.capabilities = "reconnect_required", None, []
        db.commit()
        return row
    # Owner, job and pack locks serialize disconnect/edits with this dispatch.
    result = sender.send(refreshed.access_token, row.raw_message)
    row.status, row.outcome, row.provider_status = result.status, result.code, result.http_status
    row.provider_message_id, row.provider_thread_id = result.message_id, result.thread_id
    if result.http_status in (401, 403):
        connection.status = "reconnect_required"
    if result.status == "sent":
        # A conflicting manual tracker record is preserved; acceptance is still recorded.
        try:
            with db.begin_nested():
                application = ApplicationRecord(owner_id=owner, job_id=job_id, submission_date=mailbox.now(),
                    method="email", status="Applied", pack_id=uuid.UUID(snap["pack_id"]), pack_version=snap["pack_version"],
                    cv_snapshot=snap["cv"], cover_letter_snapshot=snap["cover_letter"],
                    notes="Gmail accepted the user-approved email. Recipient delivery and reading are unverified.")
                db.add(application)
                db.flush()
                db.add(ApplicationStatusEvent(application_id=application.id, status="Applied", changed_at=mailbox.now()))
                row.application_id = application.id
        except IntegrityError:
            row.outcome = "gmail_accepted_tracking_conflict"
    db.commit()
    return row
