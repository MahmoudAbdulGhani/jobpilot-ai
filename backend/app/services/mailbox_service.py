import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.models import User, MailboxConnection, MailboxOAuthState
from app.services.mailbox_provider import MailboxError, SCOPES, seal, unseal


def now(): return datetime.now(timezone.utc)
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def context(row): return f"{row.owner_id}:{row.id}"


def owned(db, owner, connection_id):
    row = db.scalar(select(MailboxConnection).where(MailboxConnection.id == connection_id, MailboxConnection.owner_id == owner))
    if not row: raise MailboxError("not_found", 404)
    return row


def owner_lock(db, owner):
    user = db.scalar(select(User).where(User.id == owner).with_for_update())
    if not user or not user.is_active: raise MailboxError("not_found", 404)


def public(row):
    status = row.status
    if status == "connected" and row.expires_at and row.expires_at <= now(): status = "expired"
    return {"id":str(row.id), "provider":row.provider, "email":row.email,
        "capabilities":row.capabilities, "status":status, "expires_at":row.expires_at}


def start(db, owner, capabilities, connection_id, settings, provider):
    owner_lock(db, owner)
    if connection_id: owned(db, owner, connection_id)
    state, browser, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    # One active flow per owner. This also invalidates an in-flight older callback.
    db.execute(delete(MailboxOAuthState).where(MailboxOAuthState.owner_id == owner))
    hashed = digest(state)
    db.add(MailboxOAuthState(state_hash=hashed, owner_id=owner, browser_hash=digest(browser),
        verifier=seal(settings, f"{owner}:{hashed}", verifier), capabilities=sorted(set(capabilities)),
        connection_id=connection_id, expires_at=now()+timedelta(minutes=10)))
    db.commit()
    return provider.authorize(state, verifier, capabilities), browser


def finish(db, state, browser, code, denied, settings, provider):
    if not state or not browser or len(state)>128 or len(browser)>128: raise MailboxError("invalid_state", 400)
    row = db.scalar(update(MailboxOAuthState).where(
        MailboxOAuthState.state_hash == digest(state), MailboxOAuthState.browser_hash == digest(browser),
        MailboxOAuthState.consumed_at.is_(None), MailboxOAuthState.expires_at > now()
    ).values(consumed_at=now()).returning(MailboxOAuthState))
    if not row:
        db.rollback()
        raise MailboxError("invalid_state", 400)
    owner, hashed, target, requested = row.owner_id, row.state_hash, row.connection_id, row.capabilities
    encrypted_verifier = row.verifier
    row.verifier = None
    db.commit()  # Atomically consume state before any provider exchange, including denial.
    if denied: return "denied"
    if not code or len(code)>4096: raise MailboxError("invalid_callback", 400)
    token = provider.exchange(code, unseal(settings, f"{owner}:{hashed}", encrypted_verifier))
    identity = provider.identity(token.access_token)
    owner_lock(db, owner)
    # A disconnect/new flow during the exchange wins; do not resurrect credentials.
    if not db.scalar(select(MailboxOAuthState.state_hash).where(MailboxOAuthState.state_hash == hashed)):
        raise MailboxError("invalid_state", 400)
    connection = db.scalar(select(MailboxConnection).where(MailboxConnection.provider == provider.name,
        MailboxConnection.subject == identity.sub))
    if connection and connection.owner_id != owner: raise MailboxError("account_unavailable", 409)
    if target and (not connection or connection.id != target): raise MailboxError("account_mismatch", 409)
    if connection and not target:
        # A duplicate connect must not silently replace an existing grant/settings.
        db.execute(delete(MailboxOAuthState).where(MailboxOAuthState.state_hash == hashed))
        db.commit()
        return "already_connected"
    if not connection:
        import uuid
        connection = MailboxConnection(id=uuid.uuid4(), owner_id=owner, provider=provider.name,
            subject=identity.sub, email=str(identity.email), capabilities=[])
        db.add(connection)
    old = unseal(settings, context(connection), connection.credentials) if connection.credentials and not token.refresh_token else {}
    refresh = token.refresh_token or old.get("refresh_token")
    if not refresh: raise MailboxError("offline_consent_required", 409)
    granted = set(token.scope.split())
    connection.email = str(identity.email)
    connection.capabilities = [c for c in requested if SCOPES[c] in granted]
    connection.credentials = seal(settings, context(connection), {**token.model_dump(), "refresh_token":refresh})
    connection.expires_at = now()+timedelta(seconds=token.expires_in)
    connection.status = "connected"
    try:
        db.execute(delete(MailboxOAuthState).where(MailboxOAuthState.state_hash == hashed))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise MailboxError("account_unavailable", 409) from None
    return "connected" if len(connection.capabilities) == len(requested) else "partial"


def check(db, owner, connection_id, settings, provider):
    owner_lock(db, owner)
    row = owned(db, owner, connection_id)
    if row.provider != provider.name: raise MailboxError("provider_mismatch", 409)
    if not row.credentials or row.status in ("disconnected", "revoke_failed", "reconnect_required"):
        raise MailboxError("reconnect_required", 409)
    try:
        tokens = unseal(settings, context(row), row.credentials)
        # Explicit check always validates the refresh credential, without reading mail.
        refreshed = provider.refresh(tokens["refresh_token"])
        row.credentials = seal(settings, context(row), {**refreshed.model_dump(),
            "refresh_token":refreshed.refresh_token or tokens["refresh_token"]})
        row.expires_at = now()+timedelta(seconds=refreshed.expires_in)
        row.capabilities = [c for c in row.capabilities if SCOPES[c] in refreshed.scope.split()]
        row.status = "connected"
        db.commit()
    except MailboxError as error:
        if error.code in ("reconnect_required", "credential_unavailable"):
            row.status, row.credentials, row.capabilities = "reconnect_required", None, []
            db.commit()
        raise
    return public(row)


def disconnect(db, owner, connection_id, settings, provider):
    owner_lock(db, owner)
    row = owned(db, owner, connection_id)
    token = None
    failed = row.status == "revoke_failed"
    if row.credentials:
        try: token = unseal(settings, context(row), row.credentials).get("refresh_token")
        except MailboxError: failed = True
    row.credentials, row.capabilities, row.expires_at = None, [], None
    row.status = "revoke_failed" if failed else "disconnected"
    db.execute(delete(MailboxOAuthState).where(MailboxOAuthState.owner_id == owner))
    # Hold the owner lock through revocation, preventing reconnect/revoke races.
    if token:
        try:
            if provider is None or row.provider != provider.name: raise MailboxError()
            provider.revoke(token)
        except MailboxError: row.status = "revoke_failed"
    db.commit()
    return public(row)
