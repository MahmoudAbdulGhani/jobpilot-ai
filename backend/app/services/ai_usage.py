"""Shared AI request budget and bounded in-flight calls, without source payloads."""
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.models import AIUsage, JobFitAnalysis, ProfileSuggestionSet, User
from app.services.ai_provider import ProviderFailure


class AIUsageError(Exception):
    def __init__(self, status_code, message):
        self.status_code, self.message = status_code, message
        super().__init__(message)


def reserve(session, owner_id, settings):
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
    if usage.requests >= settings.JOBPILOT_AI_MAX_REQUESTS_PER_USER:
        raise AIUsageError(429, "AI request limit reached for this account.")
    token = uuid.uuid4()
    usage.requests += 1
    usage.active_token = token
    usage.active_until = now + timedelta(seconds=settings.JOBPILOT_AI_TIMEOUT_SECONDS + 10)
    return token


def release(session, owner_id, token):
    session.execute(update(AIUsage).where(AIUsage.owner_id == owner_id, AIUsage.active_token == token).values(active_token=None, active_until=None))


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
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        raise ProviderFailure("The AI request timed out. Retry with a new request.") from None
    finally:
        # A late worker returns data only; it has no DB session or write callback.
        executor.shutdown(wait=False, cancel_futures=True)
