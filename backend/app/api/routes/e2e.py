"""Test-only support endpoints used by the connected browser suites.

These endpoints exist so the Playwright suites can provision disposable
users and clean them up without depending on manually pre-seeded accounts.
They require explicit test mode and the guarded test database, returning 404
(indistinguishable from a missing route) everywhere else.
"""
import uuid
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.api.routes.auth import _require_bearer_user
from app.core.security import hash_password, hash_token, verify_password
from app.models import AccountDeletion, AccountThrottle, CandidateProfile, User
from app.services import resume_service

router = APIRouter(prefix="/e2e", tags=["test support"])
_account_tickets = {}
_usage_fixture_users: set[uuid.UUID] = set()


@router.post("/account-fixture")
def account_fixture(db: Session = Depends(get_db)):
    _require_e2e_test_mode(get_settings())
    if get_settings().JOBPILOT_ACCOUNT_MAIL_TRANSPORT != "test":
        raise HTTPException(404, "Not found")
    import secrets
    from app.services.account_service import invitation
    email = f"e2e-onboarding-{uuid.uuid4().hex}@example.com"
    ticket = secrets.token_urlsafe(32)
    _account_tickets[ticket] = email
    return {"email": email, "ticket": ticket, "invitation": invitation(db, email, 1)}


class AccountTestTicket(BaseModel):
    ticket: str = Field(min_length=20, max_length=100)


@router.post("/account-message")
def account_message(body: AccountTestTicket):
    _require_e2e_test_mode(get_settings())
    from app.services.account_mail import test_messages
    email = _account_tickets.get(body.ticket)
    if get_settings().JOBPILOT_ACCOUNT_MAIL_TRANSPORT != "test" or not email:
        raise HTTPException(404, "Not found")
    return {"text": test_messages.get(email, "")}

GENERIC_NOT_FOUND = "Not found"


@router.post("/exhaust-usage")
def exhaust_usage(user: User = Depends(_require_bearer_user), db: Session = Depends(get_db)):
    """Synthetic browser fixtures only; never dispatch a provider request."""
    settings = get_settings()
    _require_e2e_test_mode(settings)
    if not settings.JOBPILOT_AI_TEST_PROVIDER or user.id not in _usage_fixture_users or not user.email.startswith("e2e-") or not user.email.endswith("@jobpilot-test.com"):
        raise HTTPException(404, "Not found")
    from app.services import ai_usage, entitlements
    state = entitlements.snapshot(db, user.id, settings)
    if state["total"]["remaining"] > 100: raise HTTPException(409, "Synthetic fixture limit exceeded")
    for _ in range(state["total"]["remaining"]):
        state = entitlements.snapshot(db, user.id, settings)
        feature = next((name for name, row in state["features"].items() if row["remaining"] > 0), None)
        if feature is None: break
        token = ai_usage.reserve(db, user.id, settings, feature=feature)
        db.commit()  # Match the real durable pre-dispatch claim (autoflush=False).
        ai_usage.release(db, user.id, token)
        db.commit()
    return {"synthetic": True, "provider_requests_sent": 0}


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)


class CleanupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)


class BootstrapResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr


def _require_e2e_test_mode(settings: Settings) -> None:
    target = urlparse(settings.database_url).path.lstrip("/")
    if not settings.E2E_TEST_MODE or target != settings.POSTGRES_TEST_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=GENERIC_NOT_FOUND)


def _find_user(db: Session, email: str):
    return db.scalar(select(User).where(User.email == email))


@router.post("/bootstrap", response_model=BootstrapResponse)
def bootstrap_user(
    body: BootstrapRequest, db: Session = Depends(get_db)
) -> BootstrapResponse:
    _require_e2e_test_mode(get_settings())
    user = _find_user(db, body.email)
    if user is None:
        user = User(email=body.email, password_hash=hash_password(body.password))
        db.add(user)
        db.commit()
        db.refresh(user)
        _usage_fixture_users.add(user.id)
    return BootstrapResponse(user_id=user.id, email=user.email)


@router.post("/cleanup", response_model=dict)
def cleanup_user(
    body: CleanupRequest, db: Session = Depends(get_db)
) -> dict:
    _require_e2e_test_mode(get_settings())
    user = _find_user(db, body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        return {"deleted": False}
    resume_service.delete_owned_resumes(db, owner_id=user.id)
    db.execute(delete(CandidateProfile).where(CandidateProfile.owner_id == user.id))
    db.execute(delete(AccountDeletion).where(AccountDeletion.owner_id == user.id))
    db.execute(delete(AccountThrottle).where(AccountThrottle.key.in_([
        hash_token("account-data:" + str(user.id)), hash_token("email:" + user.email.lower())])))
    db.delete(user)
    db.commit()
    return {"deleted": True}
