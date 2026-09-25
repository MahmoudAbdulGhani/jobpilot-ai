"""Profile-specific quota, keyed by confirmed text instead of resume identity."""
from sqlalchemy import func, select

from app.models import ProfileGenerationRequest, ProfileSuggestionSet, User
from app.services import ai_usage, entitlements

MONTHLY_REFRESHES = 2


def _facts(db, owner_id, source_hash, settings):
    at = entitlements.now()
    start, end = entitlements.period(at)
    admin = entitlements.is_plan_admin(db, owner_id, settings)
    seen = db.scalar(select(ProfileGenerationRequest.id).where(
        ProfileGenerationRequest.owner_id == owner_id,
        ProfileGenerationRequest.source_hash == source_hash,
    ).limit(1)) is not None
    if not seen:
        # Existing suggestion sets predate the durable ledger. A deleted old
        # resume cannot be reconstructed, but surviving sets remain counted.
        seen = db.scalar(select(ProfileSuggestionSet.id).where(
            ProfileSuggestionSet.owner_id == owner_id,
            ProfileSuggestionSet.source_hash == source_hash,
        ).limit(1)) is not None
    used = db.scalar(select(func.count()).select_from(ProfileGenerationRequest).where(
        ProfileGenerationRequest.owner_id == owner_id,
        ProfileGenerationRequest.period_start == start,
        ProfileGenerationRequest.kind == "refresh",
    )) or 0
    return admin, seen, used, start, end, at


def eligibility(db, owner_id, extraction, settings):
    from app.services.profile_suggestion_service import provider_configuration, source_hash
    from app.services.privacy_service import is_consented

    source = (extraction.draft_text or "") if extraction else ""
    admin, seen, used, _, end, _ = _facts(db, owner_id, source_hash(source), settings)
    kind = "unlimited" if admin else "refresh" if seen else "initial"
    reason = None
    if not extraction or extraction.status != "succeeded" or extraction.reviewed_at is None:
        reason = "Confirm the extracted CV text before requesting suggestions."
    elif not source or len(source) > settings.JOBPILOT_AI_MAX_INPUT_CHARS:
        reason = "The confirmed CV text is empty or exceeds the AI input limit."
    elif not is_consented(db, owner_id, "ai_profile_suggestions"):
        reason = "AI data-use consent is required. Review Privacy settings before continuing."
    else:
        try:
            provider_configuration(settings)
        except Exception:
            reason = "AI profile suggestions are unavailable."
    if not admin:
        _, total, allowances, _ = entitlements.policy(db, owner_id, settings)
        consumed, by_feature = entitlements.consumption(db, owner_id, entitlements.period(entitlements.now())[0])
        if allowances["profile"] == 0:
            reason = "AI profile suggestions are unavailable on your plan."
        elif seen and used >= MONTHLY_REFRESHES:
            reason = "Two AI profile refreshes used this UTC month. A different confirmed CV gets one initial generation."
        elif seen and (consumed >= total or by_feature.get("profile", 0) >= allowances["profile"]):
            reason = "Monthly AI request allowance exhausted. A different confirmed CV gets one initial generation."
    return {"allowed": reason is None, "kind": kind,
            "remaining_refreshes": None if admin else max(0, MONTHLY_REFRESHES - used),
            "reset_at": end, "reason": reason}


def reserve(db, owner_id, source_hash, settings):
    # Serialize classification and reservation across resumes and processes.
    db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    admin, seen, used, start, _, at = _facts(db, owner_id, source_hash, settings)
    if not admin and seen and used >= MONTHLY_REFRESHES:
        raise ai_usage.AIUsageError(429, "Two AI profile refreshes used this UTC month. A different confirmed CV gets one initial generation.")
    if not admin and not seen:
        token = ai_usage.reserve(db, owner_id, settings, feature="profile", bypass_monthly_limits=True)
    else:
        token = ai_usage.reserve(db, owner_id, settings, feature="profile")
    # Fail a reservation write before adding the related source claim.
    db.flush()
    db.add(ProfileGenerationRequest(
        id=token, owner_id=owner_id, source_hash=source_hash,
        kind="admin" if admin else "refresh" if seen else "initial",
        period_start=start, created_at=at,
    ))
    return token
