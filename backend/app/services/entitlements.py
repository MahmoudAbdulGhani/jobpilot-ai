"""Server-only plan policy. No billing provider, payment state or public grants."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select, text
from app.models import AccountPlan, PlanAudit, UsageReservation, User

FEATURES = {"profile": "AI profile suggestions", "fit": "Job-fit analysis",
    "pack": "Application packs", "interview": "Text interview requests",
    "transcription": "Transcription", "speech": "Spoken questions",
    "qa": "Natural-language Q&A answers"}


class EntitlementError(Exception):
    def __init__(self, status_code, message):
        self.status_code, self.message = status_code, message
        super().__init__(message)


def now():
    return datetime.now(timezone.utc)


def is_plan_admin(db, owner, settings):
    """Case-insensitive check: does the owner's email appear in JOBPILOT_PLAN_ADMIN_EMAILS?"""
    admin_emails = settings.JOBPILOT_PLAN_ADMIN_EMAILS
    if not admin_emails:
        return False
    email = db.scalar(select(User.email).where(User.id == owner))
    if email is None:
        return False
    normalized = email.strip().lower()
    return any(normalized == e.strip().lower() for e in admin_emails)


def period(at):
    at = at.astimezone(timezone.utc)
    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


def limits(settings, name):
    configured = settings.JOBPILOT_PLAN_LIMITS[name]
    default = settings.JOBPILOT_AI_MAX_REQUESTS_PER_USER
    total = configured.total if configured.total is not None else default * (3 if name == "legacy" else 1)
    return total, {f: getattr(configured, f) if getattr(configured, f) is not None
                   else default if name == "legacy" else total for f in FEATURES}


def policy(db, owner, settings, at=None):
    at = at or now()
    row = db.get(AccountPlan, owner, populate_existing=True)
    base = row.base_plan if row else "free"
    beta = bool(row and row.beta_expires_at and row.beta_expires_at > at and row.beta_revoked_at is None)
    name = "invited_beta" if beta else base
    total, features = limits(settings, name)
    return name, total, features, row


def consumption(db, owner, start):
    counts = dict(db.execute(select(UsageReservation.feature, func.count()).where(
        UsageReservation.owner_id == owner, UsageReservation.period_start == start).group_by(UsageReservation.feature)).all())
    return sum(counts.values()), counts


def reserve(db, owner, token, feature, settings):
    # Caller must hold the active user's FOR UPDATE lock. This ledger and the
    # existing aggregate counter/lease commit in the same dispatch transaction.
    if feature not in FEATURES:
        raise EntitlementError(422, "A supported metered feature is required")
    admin = is_plan_admin(db, owner, settings)
    if not admin:
        at = now(); start, _ = period(at)
        _, total, allowances, _ = policy(db, owner, settings, at)
        used, counts = consumption(db, owner, start)
        if used >= total:
            raise EntitlementError(429, "AI request limit reached for this account's current UTC month. See Settings usage.")
        if allowances[feature] == 0:
            raise EntitlementError(403, "This feature is unavailable on your current plan. Billing is not available.")
        if counts.get(feature, 0) >= allowances[feature]:
            raise EntitlementError(429, "AI request limit reached for this account's current UTC month. See Settings usage.")
    else:
        at = now(); start, _ = period(at)
    db.add(UsageReservation(id=token, owner_id=owner, feature=feature, period_start=start, created_at=at))


def provider_available(settings, feature):
    # Metadata-only checks; never construct a provider client or make a call.
    try:
        if feature in {"transcription", "speech"}:
            from app.services.interview_voice import configuration
        elif feature == "pack":
            from app.services.application_pack_service import pack_provider_configuration as configuration
        elif feature == "interview":
            from app.services.interview_service import configuration
        else:
            from app.services.profile_suggestion_service import provider_configuration as configuration
        configuration(settings)
        return True
    except Exception:
        return False


def snapshot(db, owner, settings):
    at = now(); start, end = period(at)
    admin = is_plan_admin(db, owner, settings)
    name, total, allowances, row = policy(db, owner, settings, at)
    used, counts = consumption(db, owner, start)
    features = {}
    for feature, label in FEATURES.items():
        if admin:
            remaining = 999999
            state = "unavailable" if not provider_available(settings, feature) else "admin"
        else:
            remaining = max(0, min(allowances[feature]-counts.get(feature, 0), total-used))
            state = "unavailable" if not provider_available(settings, feature) else "not_in_plan" if allowances[feature] == 0 else "exhausted" if remaining == 0 else "available"
        features[feature] = {"label": label, "allowance": allowances[feature], "consumed": counts.get(feature, 0),
            "remaining": remaining, "state": state, "unit": "one bounded provider-request reservation"}
    return {"plan": name, "base_plan": row.base_plan if row else "free",
        "beta_expires_at": row.beta_expires_at if row else None,
        "beta_revoked_at": row.beta_revoked_at if row else None,
        "period_start": start, "reset_at": end, "reset_timezone": "UTC",
        "total": {"allowance": total, "consumed": used, "remaining": 999999 if admin else max(0, total-used)},
        "features": features, "admin": admin, "billing_available": False,
        "proposed_monthly_price_usd": str(settings.JOBPILOT_PROPOSED_MONTHLY_PRICE_USD),
        "price_note": "Business hypothesis only; no subscription or checkout is available.",
        "history_note": "Monthly accounting starts with the entitlement rollout; historical per-feature usage is not reconstructed."}


def administer(db, settings, *, email, password, owner, action, hours, reason, request_key):
    from app.services import auth_service
    from app.services.account_service import throttle
    normalized = email.strip().lower()
    # Hash-keyed throttling survives wrong credentials; never store passwords.
    throttle(db, "plan-admin:" + normalized, limit=10)
    db.execute(text("SELECT pg_advisory_xact_lock(748203196)"))
    try:
        actor = auth_service.authenticate(db, email=normalized, password=password)
    except auth_service.InvalidCredentialsError:
        raise EntitlementError(403, "Administrative authentication failed") from None
    if normalized not in settings.JOBPILOT_PLAN_ADMIN_EMAILS:
        raise EntitlementError(403, "Administrative authentication failed")
    if action not in {"grant", "revoke"} or reason not in {"invited_beta", "evaluation", "support"} or (action == "grant" and not 1 <= hours <= 2160):
        raise EntitlementError(422, "Use grant/revoke, a documented reason and a 1–2160 hour grant")
    if db.scalar(select(User.id).where(User.id == owner, User.is_active.is_(True)).with_for_update()) is None:
        raise EntitlementError(404, "Active account not found")
    hashed = hashlib.sha256(json.dumps([action, hours, reason], separators=(",", ":")).encode()).hexdigest()
    previous = db.scalar(select(PlanAudit).where(PlanAudit.owner_id == owner, PlanAudit.request_key == request_key))
    if previous:
        if previous.request_hash != hashed: raise EntitlementError(409, "Administrative request key already used")
        return previous
    row = db.get(AccountPlan, owner)
    if row is None:
        row = AccountPlan(owner_id=owner, base_plan="free"); db.add(row)
    at = now()
    if action == "grant":
        row.beta_expires_at, row.beta_revoked_at = at + timedelta(hours=hours), None
    else:
        row.beta_revoked_at = at
    audit = PlanAudit(owner_id=owner, actor_id=actor.id, request_key=request_key, request_hash=hashed,
        action=action, reason=reason, expires_at=row.beta_expires_at, created_at=at)
    db.add(audit); db.commit(); db.refresh(audit)
    return audit
