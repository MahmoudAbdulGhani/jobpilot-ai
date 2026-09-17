import html
import re
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

from sqlalchemy import select

from app.models import (ApplicationPack, ApplicationRecord, ApplicationStatusEvent, EmailApplication,
    MailboxReply, ReplySync, SavedJob)
from app.services import mailbox_service as mailbox
from app.services.email_application_service import owned, owned_job
from app.services.application_pack_service import PackError
from app.services.mailbox_provider import MailboxError, SCOPES, provider_for, seal, unseal
from app.services.reply_provider import SyncError, identifier, replies_for


def headers(message):
    result = {}
    for item in message.get("payload", {}).get("headers", []):
        name, value = item.get("name", "").lower(), item.get("value", "")
        if name in result:  # Ambiguous duplicate headers cannot confirm a match.
            result[name] = ""
        elif isinstance(value, str) and len(value) <= 16000:
            result[name] = value
    return result


def ids(value):
    return set(re.findall(r"<[^<>\s]{1,510}>", value))


def address(value):
    return [email.lower() for _, email in getaddresses([value]) if email]


def public_reply(row):
    return {"id": str(row.id), "job_id": str(row.job_id) if row.job_id else None,
        "suggested_job_id": str(row.suggested_job_id), "match_kind": row.match_kind,
        "sender": row.sender, "subject": row.subject, "preview": row.preview,
        "received_at": row.received_at, "corrected_at": row.corrected_at}


def public_sync(row):
    return {"status": row.status, "last_sync_at": row.last_sync_at, "retry_after": row.retry_after,
        "pending": len(row.progress.get("queue", [])), "more_pages": bool(row.progress.get("page")),
        "coverage": "JobPilot application thread only; text previews, no attachments"}


def reconcile(db, attempt, reader):
    original = BytesParser(policy=policy.default).parsebytes(attempt.raw_message)
    expected_id = f"<{attempt.id}@jobpilot.invalid>"
    if str(original.get("Message-ID", "")) != expected_id:
        raise SyncError("original_identifier_unavailable")
    result = reader.find_sent(expected_id)
    found = result.get("messages", [])
    if len(found) != 1 or result.get("nextPageToken"):
        raise SyncError("send_remains_unknown")
    message = reader.message(identifier(found[0]["id"]))
    h = headers(message)
    # A unique, server-generated RFC ID in Sent plus exact original envelope/date/subject.
    # No subject/sender-only inference, no attachment download and no resend.
    if (message.get("id") != found[0]["id"] or "SENT" not in message.get("labelIds", [])
        or "DRAFT" in message.get("labelIds", []) or h.get("message-id") != expected_id
        or address(h.get("from", "")) != [attempt.snapshot["sender"].lower()]
        or address(h.get("to", "")) != [attempt.snapshot["recipient"].lower()]
        or h.get("subject") != attempt.snapshot["subject"] or h.get("date") != str(original["Date"])):
        raise SyncError("send_remains_unknown")
    attempt.provider_message_id = identifier(message["id"])
    attempt.provider_thread_id = identifier(message["threadId"])
    attempt.status, attempt.outcome = "sent", "reconciled_exact_original_in_sent"
    application = db.scalar(select(ApplicationRecord).where(ApplicationRecord.owner_id == attempt.owner_id,
        ApplicationRecord.job_id == attempt.job_id))
    if not application:
        pack_id = uuid.UUID(attempt.snapshot["pack_id"])
        pack = db.scalar(select(ApplicationPack).where(ApplicationPack.id == pack_id, ApplicationPack.owner_id == attempt.owner_id,
            ApplicationPack.job_id == attempt.job_id))
        application = ApplicationRecord(owner_id=attempt.owner_id, job_id=attempt.job_id,
            submission_date=attempt.dispatch_at or attempt.created_at, method="email", status="Applied",
            pack_id=pack.id if pack else None, pack_version=attempt.snapshot["pack_version"],
            cv_snapshot=attempt.snapshot["cv"], cover_letter_snapshot=attempt.snapshot["cover_letter"],
            notes="Exact original message found in Gmail Sent during explicit synchronization. Recipient delivery/read status unknown.")
        db.add(application)
        db.flush()
        db.add(ApplicationStatusEvent(application_id=application.id, status="Applied", changed_at=mailbox.now()))
    attempt.application_id = application.id  # Preserve any existing user-edited status/content.
    return message


def save_reply(db, owner, connection, attempt, progress, message):
    message_id = identifier(message.get("id"))
    thread_id = identifier(message.get("threadId"))
    if thread_id != attempt.provider_thread_id or message_id == attempt.provider_message_id:
        return
    if {"SENT", "DRAFT"} & set(message.get("labelIds", [])):
        return
    if db.scalar(select(MailboxReply.id).where(MailboxReply.mailbox_id == connection.id, MailboxReply.message_id == message_id)):
        return  # Also preserve user corrections and dismissal tombstones.
    h = headers(message)
    if address(h.get("from", "")) == [connection.email.lower()]:
        return
    received = datetime.fromtimestamp(int(message["internalDate"]) / 1000, timezone.utc)
    if received < (attempt.dispatch_at or attempt.created_at):
        return  # Thread merging can contain messages predating the application.
    references = ids(h.get("in-reply-to", "")) | ids(h.get("references", ""))
    confirmed = bool(progress.get("root_rfc") and progress["root_rfc"] in references)
    own_ids = ids(h.get("message-id", ""))
    db.add(MailboxReply(owner_id=owner, mailbox_id=connection.id, attempt_id=attempt.id,
        suggested_job_id=attempt.job_id, job_id=attempt.job_id if confirmed else None,
        message_id=message_id, thread_id=thread_id, rfc_message_id=next(iter(own_ids)) if len(own_ids) == 1 else "",
        match_kind="reply_headers" if confirmed else "uncertain_thread", received_at=received,
        sender=h.get("from", "Sender unavailable")[:512], subject=h.get("subject", "Subject unavailable")[:512],
        preview=html.unescape(str(message.get("snippet", "Text preview unavailable")))[:2000]))


def batch(db, owner, job_id, attempt_id, settings):
    # Holding this same owner lock as disconnect/consent serializes each bounded batch.
    mailbox.owner_lock(db, owner)
    owned_job(db, owner, job_id)
    attempt = owned(db, owner, job_id, attempt_id)
    if attempt.status not in ("sent", "unknown", "sending", "simulated"):
        raise PackError(409, "Only dispatched applications can be synchronized")
    if attempt.status == "sending" and (not attempt.dispatch_at or attempt.dispatch_at > mailbox.now() - timedelta(minutes=2)):
        raise PackError(409, "Dispatch is still pending; check its outcome first")
    connection = mailbox.owned(db, owner, uuid.UUID(attempt.snapshot["mailbox_id"]))
    if connection.status != "connected" or not connection.credentials or "read_replies" not in connection.capabilities:
        raise PackError(409, "Enable reply tracking in Settings before synchronizing; sending needs no read access")
    state = db.get(ReplySync, attempt.id)
    if not state:
        state = ReplySync(attempt_id=attempt.id, owner_id=owner, mailbox_id=connection.id, progress={})
        db.add(state)
    if state.retry_after and state.retry_after > mailbox.now():
        return state
    cooldown = db.scalar(select(ReplySync.retry_after).where(ReplySync.mailbox_id == connection.id,
        ReplySync.owner_id == owner, ReplySync.retry_after > mailbox.now()).order_by(ReplySync.retry_after.desc()))
    if cooldown:
        state.status, state.retry_after = "rate_limited", cooldown
        db.commit()
        return state
    progress = deepcopy(state.progress)
    try:
        oauth = provider_for(settings)
        if connection.provider != oauth.name or attempt.snapshot["provider"] != oauth.name:
            raise SyncError("provider_mismatch")
        credentials = unseal(settings, mailbox.context(connection), connection.credentials)
        refreshed = oauth.refresh(credentials["refresh_token"])
        connection.credentials = seal(settings, mailbox.context(connection), {**refreshed.model_dump(),
            "refresh_token": refreshed.refresh_token or credentials["refresh_token"]})
        connection.expires_at = mailbox.now() + timedelta(seconds=refreshed.expires_in)
        connection.capabilities = [c for c in connection.capabilities if SCOPES[c] in refreshed.scope.split()]
        if "read_replies" not in connection.capabilities:
            raise SyncError("reading_permission_required")
        reader = replies_for(settings, refreshed.access_token, attempt)
        if attempt.status in ("unknown", "sending"):
            # A synthetic provider is never evidence of real acceptance.
            if connection.provider != "google":
                raise SyncError("send_remains_unknown")
            original = reconcile(db, attempt, reader)
            root = ids(headers(original).get("message-id", ""))
            progress["root_rfc"] = next(iter(root)) if len(root) == 1 else ""
            state.status = "send_reconciled_sync_again"
            state.progress = progress
            state.last_sync_at = mailbox.now()
            db.commit()
            return state
        if "root_rfc" not in progress:
            original = reader.message(identifier(attempt.provider_message_id))
            if original.get("id") != attempt.provider_message_id or original.get("threadId") != attempt.provider_thread_id:
                raise SyncError("original_identifier_unavailable")
            root = ids(headers(original).get("message-id", ""))
            progress["root_rfc"] = next(iter(root)) if len(root) == 1 else ""
        if not progress.get("queue"):
            if not progress.get("history"):
                checkpoint = reader.checkpoint()  # Capture before baseline to avoid losing concurrent additions.
                page = reader.thread(identifier(attempt.provider_thread_id))
                if page.get("id") != attempt.provider_thread_id:
                    raise SyncError("invalid_provider_response")
                messages = page.get("messages", [])
                page["historyId"] = checkpoint
            else:
                page = reader.history(progress["history"], progress.get("page"))
                messages = [item["message"] for h in page.get("history", []) for item in h.get("messagesAdded", [])]
            if len(messages) > 200:
                raise SyncError("response_limit")
            pending = list(dict.fromkeys(identifier(m["id"]) for m in messages
                if m.get("threadId") == attempt.provider_thread_id and m.get("id") != attempt.provider_message_id))
            next_history = identifier(page["historyId"])
            token = page.get("nextPageToken")
            if token and (not isinstance(token, str) or len(token) > 2048):
                raise SyncError("invalid_provider_response")
            progress.update(queue=pending, next_history=next_history, next_page=token)
        for _ in range(min(5, len(progress.get("queue", [])))):
            message_id = progress["queue"][0]
            if db.scalar(select(MailboxReply.id).where(MailboxReply.mailbox_id == connection.id, MailboxReply.message_id == message_id)):
                progress["queue"].pop(0)
                continue  # Do not download an already saved or dismissed preview again.
            try:
                message = reader.message(message_id)
                if message.get("id") != message_id:
                    raise SyncError("invalid_provider_response")
                save_reply(db, owner, connection, attempt, progress, message)
            except SyncError as error:
                if error.code != "message_unavailable":
                    raise
            progress["queue"].pop(0)
        if not progress.get("queue"):
            progress["page"] = progress.pop("next_page", None)
            if not progress["page"]:
                progress["history"] = progress["next_history"]
            progress.pop("next_history", None)
        state.status = "more_pending" if progress.get("queue") or progress.get("page") else "up_to_date_for_thread"
        state.retry_after = None
    except (SyncError, MailboxError) as error:
        state.status = error.code
        if error.code == "history_expired":
            progress = {"root_rfc": progress.get("root_rfc", "")}
        if error.code == "page_expired":
            progress["page"] = None
        if error.code == "rate_limited":
            state.retry_after = mailbox.now() + timedelta(seconds=error.retry_seconds)
        if error.code == "reading_permission_required":
            connection.capabilities = [c for c in connection.capabilities if c != "read_replies"]
        if error.code in ("credential_revoked", "reconnect_required", "credential_unavailable"):
            connection.status, connection.credentials, connection.capabilities = "reconnect_required", None, []
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
        state.status = "invalid_provider_response"
    state.progress = progress
    state.last_sync_at = mailbox.now()
    db.commit()  # Replies and cursor move atomically; errors preserve the unprocessed queue.
    return state


def correct(db, owner, reply_id, job_id):
    mailbox.owner_lock(db, owner)
    reply = db.scalar(select(MailboxReply).where(MailboxReply.id == reply_id, MailboxReply.owner_id == owner))
    if not reply:
        raise PackError(404, "Reply not found")
    if job_id:
        owned_job(db, owner, job_id)
        reply.job_id, reply.match_kind = job_id, "user_confirmed"
    else:
        reply.job_id, reply.match_kind = None, "dismissed"
        reply.sender, reply.subject, reply.preview, reply.rfc_message_id = "", "", "", ""
    reply.corrected_at = mailbox.now()
    db.commit()
    return reply
