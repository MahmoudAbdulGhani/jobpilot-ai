from typing import Literal
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import clear_auth_cookies
from app.api.routes.auth import _require_bearer_user
from app.services import account_service as service

router = APIRouter(prefix="/account", tags=["account"])


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=255)


class RegisterRequest(EmailRequest):
    password: str = Field(min_length=12, max_length=128)
    invitation: str | None = Field(default=None, max_length=100)


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=100)


class ResetRequest(TokenRequest):
    password: str = Field(min_length=12, max_length=128)


def guard(db, request, email=""):
    service.throttle(db, "ip:" + (request.client.host if request.client else "unknown"), 30)
    if email:
        service.throttle(db, "email:" + email.lower())


@router.get("/options")
def options():
    return {"registration": get_settings().JOBPILOT_REGISTRATION}


@router.post("/register")
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = str(body.email).lower()
    guard(db, request, email)
    service.register(db, get_settings(), email, body.password, body.invitation)
    return {"message": "Account email accepted by the transport. Check your inbox for available next steps; delivery is not guaranteed."}


@router.post("/request/{purpose}")
def request_link(purpose: Literal["verify", "reset"], body: EmailRequest, request: Request, db: Session = Depends(get_db)):
    email = str(body.email).lower()
    guard(db, request, email)
    service.request_link(db, get_settings(), email, purpose)
    return {"message": "Account email accepted by the transport. If an eligible account exists, it contains the next step. Delivery is not guaranteed."}


@router.post("/verify")
def verify(body: TokenRequest, request: Request, db: Session = Depends(get_db)):
    guard(db, request)
    service.finish(db, body.token, "verify")
    return {"message": "Email verified. You can now sign in."}


@router.post("/reset")
def reset(body: ResetRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    guard(db, request)
    service.finish(db, body.token, "reset", body.password)
    clear_auth_cookies(response)
    return {"message": "Password changed. All previous sessions are invalid. Sign in with your new password."}


class OnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: Literal["profile", "cv", "job", "done"]


@router.get("/onboarding")
def onboarding(user=Depends(_require_bearer_user)):
    return {"step": user.onboarding_step, "ai_enabled": get_settings().JOBPILOT_AI_ENABLED}


@router.patch("/onboarding")
def update_onboarding(body: OnboardingRequest, user=Depends(_require_bearer_user), db: Session = Depends(get_db)):
    user.onboarding_step = body.step
    db.commit()
    return {"step": user.onboarding_step, "ai_enabled": get_settings().JOBPILOT_AI_ENABLED}
