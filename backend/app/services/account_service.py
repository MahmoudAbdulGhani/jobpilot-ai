import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from app.core.security import hash_password, hash_token
from app.models import AccountToken, AccountThrottle, User, RefreshToken
from app.services import account_mail


def now():
    return datetime.now(timezone.utc)


def throttle(db, key, limit=5):
    digest = hash_token(key)
    db.execute(insert(AccountThrottle).values(key=digest, window_start=now(), attempts=0).on_conflict_do_nothing())
    row = db.scalar(select(AccountThrottle).where(AccountThrottle.key == digest).with_for_update())
    if row.window_start < now() - timedelta(hours=1):
        row.window_start, row.attempts = now(), 0
    row.attempts += 1
    blocked = row.attempts > limit
    db.commit()  # Attempts survive invalid tokens and failed deliveries.
    if blocked:
        raise HTTPException(429, "Too many account requests; try again later", headers={"Retry-After": "3600"})


def email_lock(db, email):
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(hash_token(email)[:15], 16)})


def token(db, purpose, email, user_id=None, hours=1):
    raw = secrets.token_urlsafe(32)
    db.add(AccountToken(token_hash=hash_token(raw), purpose=purpose, email=email,
                        user_id=user_id, expires_at=now() + timedelta(hours=hours)))
    return raw


def consume(db, raw, purpose):
    row = db.scalar(select(AccountToken).where(AccountToken.token_hash == hash_token(raw),
                    AccountToken.purpose == purpose).with_for_update().execution_options(populate_existing=True))
    if not row or row.consumed_at or row.expires_at <= now():
        raise HTTPException(400, "This link is invalid or expired")
    row.consumed_at = now()
    return row


def invitation(db, email, hours):
    if not 1 <= hours <= 168:
        raise ValueError("Invitation lifetime must be 1–168 hours")
    raw = token(db, "invite", email.strip().lower(), hours=hours)
    db.commit()
    return raw


def register(db, settings, email, password, invite):
    if settings.JOBPILOT_REGISTRATION == "closed":
        raise HTTPException(403, "Registration is closed")
    account_mail.configured(settings)
    email_lock(db, email)
    invitation_row = None
    if settings.JOBPILOT_REGISTRATION == "invite-only":
        invitation_row = consume(db, invite or "", "invite")
        if invitation_row.email != email:
            raise HTTPException(400, "This link is invalid or expired")
    user = db.scalar(select(User).where(User.email == email))
    password_hash = hash_password(password)  # Same expensive work for duplicate accounts.
    raw = None
    if not user:
        user = User(email=email, password_hash=password_hash, email_verified=False, onboarding_step="profile")
        db.add(user)
        db.flush()
        raw = token(db, "verify", email, user.id, hours=24)
    account_mail.send(settings, email, "verify", raw)
    db.commit()


def request_link(db, settings, email, purpose):
    account_mail.configured(settings)
    email_lock(db, email)
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    raw = None
    if user and (purpose == "reset" or not user.email_verified):
        raw = token(db, purpose, email, user.id, hours=1 if purpose == "reset" else 24)
    # Unknown/verified addresses receive a neutral message too: same transport
    # outcome and public response, without revealing account existence.
    account_mail.send(settings, email, purpose, raw)
    db.commit()


def finish(db, raw, purpose, password=None):
    # Serialize all credentials changes for an account before locking tokens.
    candidate = db.get(AccountToken, hash_token(raw))
    if candidate and candidate.user_id:
        db.scalar(select(User).where(User.id == candidate.user_id).with_for_update())
    row = consume(db, raw, purpose)
    user = db.scalar(select(User).where(User.id == row.user_id).with_for_update().execution_options(populate_existing=True))
    if not user or not user.is_active:
        raise HTTPException(400, "This link is invalid or expired")
    if purpose == "verify":
        user.email_verified = True
    else:
        user.password_hash = hash_password(password)
        user.session_version += 1
        db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked_at=now()))
    db.execute(update(AccountToken).where(AccountToken.user_id == user.id,
               AccountToken.purpose == purpose, AccountToken.consumed_at.is_(None)).values(consumed_at=now()))
    db.commit()
