"""Shared AI request budget and bounded in-flight calls, without source payloads."""
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.models import AIPilotDispatch, AIUsage, JobFitAnalysis, ProfileSuggestionSet, User, UsageReservation
from app.services.ai_provider import ProviderFailure


class AIUsageError(Exception):
    def __init__(self, status_code, message):
        self.status_code, self.message = status_code, message
        super().__init__(message)


def reserve(session, owner_id, settings, feature=None, *, bypass_monthly_limits=False):
    if settings.ENVIRONMENT == "production" and settings.JOBPILOT_AI_PILOT_ENABLED:
        if str(owner_id) != settings.JOBPILOT_AI_PILOT_ACCOUNT_ID or feature != "profile":
            raise AIUsageError(503, "AI is unavailable outside the profile pilot.")
    # Serialize quota allocation across all AI tasks/processes, but release the
    # lock with the caller's pre-provider commit. Never lock during network I/O.
    if session.scalar(select(User.id).where(User.id == owner_id, User.is_active.is_(True)).with_for_update()) is None:
        raise AIUsageError(404, "User not found")
    usage = session.get(AIUsage, owner_id, populate_existing=True)
    if usage is None:
        previous = sum(session.scalar(select(func.count()).select_from(model).where(model.owner_id == owner_id)) or 0 for model in (JobFitAnalysis, ProfileSuggestionSet))
        usage = AIUsage(owner_id=owner_id, requests=previous)
        session.add(usage)
    now = datetime.now(timezone.utc)
    if usage.active_until and usage.active_until > now:
        raise AIUsageError(409, "An AI request is already in progress. Wait for it to finish.")
    token = uuid.uuid4()
    from app.services.entitlements import reserve as reserve_entitlement, EntitlementError
    try:
        reserve_entitlement(session, owner_id, token, feature, settings,
                            bypass_monthly_limits=bypass_monthly_limits)
    except EntitlementError as error:
        raise AIUsageError(error.status_code, error.message) from None
    usage.requests += 1
    usage.active_token = token
    usage.active_until = now + timedelta(seconds=settings.JOBPILOT_AI_TIMEOUT_SECONDS + 10)
    return token


def claim_pilot_dispatch(session, owner_id, settings):
    """Consume the one-shot claim before HTTP dispatch; ambiguous failures stay consumed."""
    if settings.ENVIRONMENT != "production" or not settings.JOBPILOT_AI_PILOT_ENABLED:
        return
    if str(owner_id) != settings.JOBPILOT_AI_PILOT_ACCOUNT_ID:
        raise AIUsageError(503, "AI profile pilot is unavailable.")
    claimed = session.execute(update(AIPilotDispatch).where(
        AIPilotDispatch.id == 1, AIPilotDispatch.claimed_at.is_(None),
    ).values(owner_id=owner_id, feature="profile", claimed_at=datetime.now(timezone.utc))
        .returning(AIPilotDispatch.id)).scalar_one_or_none()
    if claimed is None:
        raise AIUsageError(409, "The production AI pilot request has already been used.")
    session.commit()


def release(session, owner_id, token):
    session.execute(update(AIUsage).where(AIUsage.owner_id == owner_id, AIUsage.active_token == token).values(active_token=None, active_until=None))
    session.execute(update(UsageReservation).where(UsageReservation.owner_id == owner_id, UsageReservation.id == token).values(released_at=datetime.now(timezone.utc)))


def dispatch_guard(session, owner_id):
    """Recheck the active account after the durable dispatch claim.

    A provider request already dispatched cannot be recalled. A timed-out worker
    returns data only; database triggers reject any later inactive-owner writes.
    """
    from fastapi import HTTPException
    if session.scalar(select(User.id).where(User.id == owner_id, User.is_active.is_(True))) is None:
        raise HTTPException(410, "Account unavailable")


def bounded_call(operation, timeout):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-request")
    future = executor.submit(operation)
    started = time.monotonic()
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        from app.services.ai_provider import _timeout_diagnostic
        raise ProviderFailure(
            "timeout",
            diagnostic=_timeout_diagnostic("outer", timeout, time.monotonic() - started),
        ) from None
    finally:
        # A late worker returns data only; it has no DB session or write callback.
        executor.shutdown(wait=False, cancel_futures=True)
