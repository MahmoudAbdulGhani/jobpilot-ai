from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.profile import CandidateProfileResponse, CandidateProfileUpdate
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["candidate profile"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=CandidateProfileResponse)
def get_profile(db: Database, current_user: CurrentUser) -> CandidateProfileResponse:
    profile = profile_service.get_candidate_profile(db, owner_id=current_user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.patch("", response_model=CandidateProfileResponse)
def update_profile(
    body: CandidateProfileUpdate,
    db: Database,
    current_user: CurrentUser,
) -> CandidateProfileResponse:
    return profile_service.upsert_candidate_profile(
        db, owner_id=current_user.id, data=body
    )