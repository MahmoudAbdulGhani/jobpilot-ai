"""Account lifecycle operations. Never log content, credentials or receipts."""
import io
import json
import secrets
import time
import zipfile
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import Text, case, delete, func, select, text, update
from app.models import (Base, User, Resume, RefreshToken, AccountToken, AccountThrottle,
    MailboxOAuthState, MailboxConnection, MailboxReply, AccountExport, AccountDeletion, InterviewVoiceOperation)
from app.core.security import hash_token, verify_password
from app.services.account_service import now, throttle
from app.services import resume_store, mailbox_service
from app.services.mailbox_provider import MailboxError, provider_for, unseal

# Reviewed allowlist: future columns/tables are NOT automatically exported.
EXPORT_COLUMNS = {
    "users": "id email is_active email_verified onboarding_step created_at updated_at",
    "candidate_profiles": "id headline target_roles location remote_preference work_authorization skills experience education languages salary_preference ai_provenance created_at updated_at",
    "saved_jobs": "id title company location description source_url notes source_provider source_external_id source_snapshot imported_at is_archived created_at updated_at",
    "resumes": "id original_filename display_name file_extension size_bytes is_primary created_at updated_at",
    "resume_extractions": "id resume_id status original_text draft_text parser_name parser_version failure_code failure_message reviewed_at created_at updated_at",
    "applications": "id job_id submission_date method notes status reminder_status reminder_timezone reminder_revision follow_up_date pack_id pack_version cv_snapshot cover_letter_snapshot created_at updated_at",
    "application_status_events": "id application_id status changed_at created_at updated_at",
    "application_packs": "id job_id profile_id resume_id extraction_id source_snapshot status current_version generated review_notes provider model prompt_version outcome_message created_at updated_at",
    "application_pack_versions": "id pack_id number cv cover_letter approved_at created_at updated_at",
    "interview_sessions": "id job_id source_snapshot configuration mode question_count status revision turns created_at updated_at",
    "interview_operations": "id session_id step status outcome usage created_at updated_at",
    "interview_voice_operations": "id session_id kind question_number status outcome configuration usage transcript expires_at created_at updated_at",
    "profile_suggestion_sets": "id resume_id extraction_id source_text source_reviewed_at status suggestions provider model prompt_version outcome_message applied_at apply_result created_at updated_at",
    "job_fit_analyses": "id job_id profile_id job_snapshot profile_facts status result counts provider model prompt_version outcome_message created_at updated_at",
    "email_applications": "id job_id application_id snapshot status approved_at dispatch_at provider_message_id provider_thread_id outcome provider_status created_at updated_at",
    "mailbox_connections": "id provider email capabilities status expires_at created_at updated_at",
    "mailbox_replies": "id mailbox_id attempt_id suggested_job_id job_id message_id thread_id rfc_message_id match_kind sender subject preview received_at corrected_at created_at updated_at",
    "reply_syncs": "attempt_id mailbox_id status last_sync_at retry_after created_at updated_at",
    "ai_usage": "requests",
}
PARENTS = {"resume_extractions": ("resume_id", "resumes"),
    "application_pack_versions": ("pack_id", "application_packs"),
    "interview_operations": ("session_id", "interview_sessions"),
    "application_status_events": ("application_id", "applications")}


def reauthenticate(db, owner, password):
    active_owner(db, owner)  # Do not recreate an owner-specific throttle after deletion.
    throttle(db, "account-data:" + str(owner), limit=5)
    user = active_owner(db, owner)
    if not verify_password(password, user.password_hash):
        raise HTTPException(403, "Reauthentication failed")
    return user


def active_owner(db, owner):
    try: return mailbox_service.owner_lock(db, owner)
    except MailboxError: raise HTTPException(410, "Account unavailable") from None


def has_recovery_account(db, owner):
    return db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True), User.email_verified.is_(True), User.id != owner)) > 0


def export_query(name, owner):
    table = Base.metadata.tables[name]
    columns = [table.c[c] for c in EXPORT_COLUMNS[name].split()]
    if name == "interview_voice_operations":
        columns = [case((table.c.expires_at > now(), c), else_=None).label("transcript")
                   if c.name == "transcript" else c for c in columns]
    if name == "users": condition = table.c.id == owner
    elif "owner_id" in table.c: condition = table.c.owner_id == owner
    else:
        fk, parent = PARENTS[name]
        parent = Base.metadata.tables[parent]
        condition = table.c[fk].in_(select(parent.c.id).where(parent.c.owner_id == owner))
    return select(*columns).where(condition)


def create_export(db, owner, password, settings):
    user = reauthenticate(db, owner, password)
    # Account lock serializes exports/deletion and ownership write barriers.
    db.execute(text("SET LOCAL statement_timeout = '15000ms'"))
    limit = settings.ACCOUNT_EXPORT_MAX_MIB * 1024 * 1024
    deadline = time.monotonic() + 60
    budget, rows_left = limit, settings.ACCOUNT_EXPORT_MAX_ROWS
    data = {}; resumes = []
    for name in EXPORT_COLUMNS:
        if time.monotonic() > deadline: raise HTTPException(503, "Export time limit reached; contact the local operator")
        query = export_query(name, owner)
        # Size each row in PostgreSQL before transferring any potentially large JSON.
        sub = query.subquery()
        count, size = db.execute(select(func.count(), func.coalesce(func.sum(func.octet_length(func.row_to_json(sub.table_valued()).cast(Text))), 0))).one()
        rows_left -= count
        budget -= size
        if rows_left < 0 or budget < 0:
            raise HTTPException(413, "Export exceeds the configured limit; contact the local operator")
        data[name] = [dict(row) for row in db.execute(query).mappings()]
    payload = json.dumps(data, default=str, ensure_ascii=False).encode()
    if len(payload) > limit: raise HTTPException(413, "Export exceeds the configured limit")
    budget = limit - len(payload)
    if len(data["resumes"]) > 32: raise HTTPException(413, "Export exceeds the 32-document limit; contact the local operator")
    for row in data["resumes"]:
        budget -= row["size_bytes"]
        if budget < 0: raise HTTPException(413, "Export exceeds the configured limit")
        resumes.append(row)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("account.json", payload)
        archive.writestr("README.txt", "Private JobPilot export. Original uploads are under documents/<id>. Email attachments are base64 in email_applications.snapshot.attachments. Reviewed CVs/packs and interview feedback are structured JSON. Excluded: passwords, authentication tokens/hashes, OAuth credentials/state, internal idempotency keys, global throttles, duplicate raw MIME, deleted/expired data and historical backups. This archive contains sensitive personal content; store securely.")
        for row in resumes:
            if time.monotonic() > deadline: raise HTTPException(503, "Export time limit reached; contact the local operator")
            content = resume_store.read_bytes(row["id"])
            if content is None or len(content) != row["size_bytes"]:
                raise HTTPException(503, "A private document is unavailable; export was not completed")
            archive.writestr("documents/" + str(row["id"]), content)
    if stream.tell() > limit: raise HTTPException(413, "Export exceeds the configured limit")
    db.execute(delete(AccountExport).where(AccountExport.owner_id == owner))
    row = AccountExport(owner_id=owner, session_version=user.session_version,
        archive=stream.getvalue(), expires_at=now() + timedelta(minutes=settings.ACCOUNT_EXPORT_MINUTES))
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "expires_at": row.expires_at, "size_bytes": stream.tell()}


def download(db, user, export_id):
    user = active_owner(db, user.id)
    row = db.scalar(select(AccountExport).where(AccountExport.id == export_id,
        AccountExport.owner_id == user.id, AccountExport.expires_at > now(),
        AccountExport.session_version == user.session_version))
    if not row: raise HTTPException(404, "Export unavailable or expired; reauthenticate to create another")
    return row.archive


def request_deletion(db, owner, password, confirmation):
    if confirmation != "DELETE MY ACCOUNT": raise HTTPException(422, "Type DELETE MY ACCOUNT to confirm")
    # Serialize last-account checks across different owners. Same lock as bootstrap.
    from app.services.auth_service import OWNER_BOOTSTRAP_LOCK_ID
    # throttle commits; acquire global lock only after it returns.
    user = reauthenticate(db, owner, password)
    # Release the owner lock before global lock to avoid reversed lock order.
    db.commit()
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": OWNER_BOOTSTRAP_LOCK_ID})
    user = active_owner(db, owner)
    if not verify_password(password, user.password_hash): raise HTTPException(403, "Reauthentication failed")
    if not has_recovery_account(db, owner):
        raise HTTPException(409, "The last active account is protected. A local operator must establish a verified recovery account before deletion")
    receipt = secrets.token_urlsafe(32)
    row = AccountDeletion(owner_id=owner, receipt_hash=hash_token(receipt))
    db.add(row)
    db.execute(delete(RefreshToken).where(RefreshToken.user_id == owner))
    db.execute(delete(AccountToken).where((AccountToken.user_id == owner) | (AccountToken.email == user.email)))
    db.execute(delete(MailboxOAuthState).where(MailboxOAuthState.owner_id == owner))
    db.execute(delete(AccountExport).where(AccountExport.owner_id == owner))
    user.is_active = False; user.session_version += 1
    db.commit(); db.refresh(row)
    return {"id": str(row.id), "receipt": receipt, "status": "pending"}


def status(db, deletion_id, receipt):
    row = db.scalar(select(AccountDeletion).where(AccountDeletion.id == deletion_id,
        AccountDeletion.receipt_hash == hash_token(receipt)))
    if not row: raise HTTPException(404, "Deletion receipt unavailable")
    return {"status": row.status, "failure": row.failure,
        "provider_revocation_unconfirmed": row.revocation_unconfirmed, "completed_at": row.completed_at}


def cleanup_deletion(db, deletion_id, settings, *, batch_size=20):
    """One bounded resumable batch. File metadata remains until deletion succeeds.

    A crashed revocation attempt is uncertain; never replay it automatically.
    Local removal continues with an explicit unconfirmed-revocation warning.
    """
    if not 1 <= batch_size <= 20: raise ValueError("batch_size must be 1–20")
    row = db.scalar(select(AccountDeletion).where(AccountDeletion.id == deletion_id).with_for_update(skip_locked=True).execution_options(populate_existing=True))
    if not row or row.status == "complete": return
    if row.lease_until and row.lease_until > now(): return
    row.lease_until = now() + timedelta(minutes=5)
    user = db.scalar(select(User).where(User.id == row.owner_id).with_for_update())
    if user and user.is_active: raise RuntimeError("Deletion requires an inactive account")
    # Claim before external revocation. Retries must not repeat provider requests.
    if not row.revocation_attempts:
        row.revocation_attempts = 1
        row.revocation_unconfirmed = bool(db.scalar(select(MailboxConnection.id).where(MailboxConnection.owner_id == row.owner_id, MailboxConnection.credentials.is_not(None)).limit(1)))
        db.commit()
        row = db.scalar(select(AccountDeletion).where(AccountDeletion.id == deletion_id).with_for_update())
        failed = False
        connections = list(db.scalars(select(MailboxConnection).where(MailboxConnection.owner_id == row.owner_id).limit(batch_size + 1)))
        if len(connections) > batch_size: failed = True
        for connection in connections[:batch_size]:
            if not connection.credentials: continue
            try:
                provider = provider_for(settings)
                if provider.name != connection.provider: raise ValueError()
                tokens = unseal(settings, mailbox_service.context(connection), connection.credentials)
                provider.revoke(tokens["refresh_token"])
            except Exception:
                failed = True  # Never retain exception text or token/provider bodies.
        row.revocation_unconfirmed = failed
    try:
        db.execute(text("SET LOCAL statement_timeout = '30000ms'"))
        resumes = list(db.scalars(select(Resume).where(Resume.owner_id == row.owner_id).order_by(Resume.id).limit(batch_size)))
        for resume in resumes:
            resume_store.delete_bytes(resume.id)
            db.delete(resume)
            db.flush()
        remaining = db.scalar(select(func.count()).select_from(Resume).where(Resume.owner_id == row.owner_id))
        if remaining:
            row.status, row.failure = "pending", None
        else:
            # Explicit email-bound invitations too; global IP/address throttles age out.
            if user:
                db.execute(delete(AccountToken).where(AccountToken.email == user.email))
                db.execute(delete(AccountThrottle).where(AccountThrottle.key.in_([
                    hash_token("account-data:" + str(user.id)), hash_token("email:" + user.email.lower())])))
                db.execute(delete(User).where(User.id == row.owner_id))
            row.status, row.failure, row.completed_at = "complete", None, now()
        row.lease_until = None
        db.commit()
    except Exception:
        db.rollback()
        row = db.scalar(select(AccountDeletion).where(AccountDeletion.id == deletion_id).with_for_update())
        row.status, row.failure = "failed", "local_cleanup_unconfirmed"
        row.lease_until = None
        db.commit()


def voice_retention(db, cutoff, *, dry_run=True, batch_size=100):
    condition = (InterviewVoiceOperation.expires_at <= cutoff) & InterviewVoiceOperation.transcript.is_not(None) & InterviewVoiceOperation.owner_id.in_(select(User.id).where(User.is_active.is_(True)))
    count = db.scalar(select(func.count()).select_from(InterviewVoiceOperation).where(condition))
    if not dry_run:
        ids = select(InterviewVoiceOperation.id).where(condition).order_by(InterviewVoiceOperation.id).limit(batch_size).with_for_update(skip_locked=True)
        db.execute(update(InterviewVoiceOperation).where(InterviewVoiceOperation.id.in_(ids)).values(transcript=None))
    return count


def retention(db, settings, *, dry_run=True, batch_size=100):
    """Counts only. Bounded mutation; repeat until eligible counts reach zero."""
    cutoff = now()
    token_cutoff = cutoff - timedelta(days=settings.ACCOUNT_TOKEN_RETENTION_DAYS)
    operations_cutoff = cutoff - timedelta(days=settings.ACCOUNT_OPERATION_RETENTION_DAYS)
    preview_cutoff = cutoff - timedelta(days=settings.ACCOUNT_EMAIL_PREVIEW_DAYS)
    rules = [
        (AccountExport, AccountExport.expires_at <= cutoff),
        (AccountToken, AccountToken.expires_at <= token_cutoff),
        (MailboxOAuthState, MailboxOAuthState.expires_at <= token_cutoff),
        (RefreshToken, RefreshToken.expires_at <= token_cutoff),
        (AccountThrottle, AccountThrottle.window_start <= operations_cutoff),
        (AccountDeletion, (AccountDeletion.status == "complete") & (AccountDeletion.completed_at <= operations_cutoff)),
    ]
    counts = {}
    for model, condition in rules:
        counts[model.__tablename__] = db.scalar(select(func.count()).select_from(model).where(condition))
        if not dry_run:
            pk = list(model.__table__.primary_key)[0]
            ids = select(pk).where(condition).order_by(pk).limit(batch_size).with_for_update(skip_locked=True)
            db.execute(delete(model).where(pk.in_(ids)))
    condition = (MailboxReply.received_at <= preview_cutoff) & (MailboxReply.preview != "") & MailboxReply.owner_id.in_(select(User.id).where(User.is_active.is_(True)))
    counts["email_previews"] = db.scalar(select(func.count()).select_from(MailboxReply).where(condition))
    counts["pending_deletions"] = db.scalar(select(func.count()).select_from(AccountDeletion).where(AccountDeletion.status != "complete"))
    counts["voice_transcripts"] = voice_retention(db, cutoff, dry_run=dry_run, batch_size=batch_size)
    if not dry_run:
        ids = select(MailboxReply.id).where(condition).order_by(MailboxReply.id).limit(batch_size).with_for_update(skip_locked=True)
        db.execute(update(MailboxReply).where(MailboxReply.id.in_(ids)).values(preview=""))
        db.commit()
    return counts
