import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.profile_suggestions import ApplySuggestionRequest, SuggestionSetResponse
from app.schemas.profile import CandidateProfileResponse
from app.services import profile_service, profile_suggestion_service, resume_service

router = APIRouter(prefix="/profile-suggestions", tags=["AI profile suggestions"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


def owned_or_404(db, user, suggestion_id):
    record = profile_suggestion_service.get_owned(db, owner_id=user.id, suggestion_id=suggestion_id)
    if record is None:
        raise HTTPException(404, "Suggestion set not found")
    return record


@router.post("/resumes/{resume_id}", response_model=SuggestionSetResponse)
def generate(resume_id: uuid.UUID, db: Database, current_user: CurrentUser):
    resume = resume_service.get_resume(db, owner_id=current_user.id, resume_id=resume_id)
    if resume is None:
        raise HTTPException(404, "Resume not found")
    try:
        settings = get_settings()
        if settings.JOBPILOT_AI_PROVIDER == "openai" and not settings.JOBPILOT_AI_TEST_PROVIDER:
            return profile_suggestion_service.queue_generation(
                db, owner_id=current_user.id, resume=resume, settings=settings,
            )
        return profile_suggestion_service.generate(
            db, owner_id=current_user.id, resume=resume, settings=settings,
        )
    except profile_suggestion_service.SuggestionError as error:
        raise HTTPException(error.status_code, error.message) from error


@router.get("/resumes/{resume_id}/latest", response_model=SuggestionSetResponse)
def latest(resume_id: uuid.UUID, db: Database, current_user: CurrentUser):
    resume = resume_service.get_resume(db, owner_id=current_user.id, resume_id=resume_id)
    if resume is None:
        raise HTTPException(404, "Resume not found")
    record = profile_suggestion_service.latest_for_resume(
        db, owner_id=current_user.id, resume_id=resume.id
    )
    if record is None:
        raise HTTPException(404, "Suggestion set not found")
    return record


@router.get("/{suggestion_id}", response_model=SuggestionSetResponse)
def get(suggestion_id: uuid.UUID, db: Database, current_user: CurrentUser):
    return owned_or_404(db, current_user, suggestion_id)


@router.post("/{suggestion_id}/apply", response_model=SuggestionSetResponse)
def apply(suggestion_id: uuid.UUID, body: ApplySuggestionRequest, db: Database, current_user: CurrentUser):
    record = owned_or_404(db, current_user, suggestion_id)
    try:
        applied = profile_suggestion_service.apply(db, record=record, selections=body.selections)
        response = SuggestionSetResponse.model_validate(applied)
        profile = profile_service.get_candidate_profile(db, owner_id=current_user.id)
        return response.model_copy(update={
            "profile": None if profile is None else CandidateProfileResponse.model_validate(profile),
        })
    except profile_suggestion_service.SuggestionError as error:
        raise HTTPException(error.status_code, error.message) from error


@router.delete("/{suggestion_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(suggestion_id: uuid.UUID, db: Database, current_user: CurrentUser):
    record = owned_or_404(db, current_user, suggestion_id)
    if record.applied_at:
        raise HTTPException(409, "Applied suggestion history cannot be discarded.")
    db.delete(record)
    db.commit()
    return Response(status_code=204)
