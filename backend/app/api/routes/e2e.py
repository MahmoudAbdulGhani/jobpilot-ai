"""Test-only support endpoints used by the connected browser suites.

These endpoints exist so the Playwright suites can provision disposable
users and clean them up without depending on manually pre-seeded accounts.
They refuse to run against anything but the guarded test database, returning
404 (indistinguishable from a missing route) everywhere else.
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
from app.core.security import hash_password
from app.models import CandidateProfile, User
from app.services import resume_service

router = APIRouter(prefix="/e2e", tags=["test support"])

GENERIC_NOT_FOUND = "Not found"


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)


class CleanupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)


class BootstrapResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr


def _require_test_database(settings: Settings) -> None:
    target = urlparse(settings.database_url).path.lstrip("/")
    if target != settings.POSTGRES_TEST_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=GENERIC_NOT_FOUND)


def _find_user(db: Session, email: str):
    return db.scalar(select(User).where(User.email == email))


@router.post("/bootstrap", response_model=BootstrapResponse)
def bootstrap_user(
    body: BootstrapRequest, db: Session = Depends(get_db)
) -> BootstrapResponse:
    _require_test_database(get_settings())
    user = _find_user(db, body.email)
    if user is None:
        user = User(email=body.email, password_hash=hash_password(body.password))
        db.add(user)
        db.commit()
        db.refresh(user)
    return BootstrapResponse(user_id=user.id, email=user.email)


@router.post("/cleanup", response_model=dict)
def cleanup_user(
    body: CleanupRequest, db: Session = Depends(get_db)
) -> dict:
    _require_test_database(get_settings())
    user = _find_user(db, body.email)
    if user is None:
        return {"deleted": False}
    resume_service.delete_owned_resumes(db, owner_id=user.id)
    db.execute(delete(CandidateProfile).where(CandidateProfile.owner_id == user.id))
    db.delete(user)
    db.commit()
    return {"deleted": True}