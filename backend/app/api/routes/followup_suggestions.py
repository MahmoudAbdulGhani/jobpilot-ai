"""Follow-up suggestions: persisted drafts with explicit approve/reject."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.followup_suggestions import (
    SuggestionDecisionRequest, SuggestionList, SuggestionResponse)
from app.services import followup_service as service

router = APIRouter(prefix="/followup-suggestions", tags=["follow-up assistance"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.post("/generate", response_model=list[SuggestionResponse])
def generate(db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return [service.present(db, row) for row in service.generate(db, current_user.id)]


@router.get("", response_model=SuggestionList)
def listing(db: Database, current_user: CurrentUser, response: Response,
            state: Annotated[str | None, Query()] = None,
            page: Annotated[int, Query(ge=1)] = 1,
            page_size: Annotated[int, Query(ge=1, le=50)] = 20):
    response.headers["Cache-Control"] = "no-store"
    return service.listing(db, owner_id=current_user.id, state=state, page=page, page_size=page_size)


@router.post("/{suggestion_id}/approve", response_model=SuggestionResponse)
def approve(suggestion_id: uuid.UUID, body: SuggestionDecisionRequest,
            db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _ = body.confirm
    return service.approve(db, owner_id=current_user.id, suggestion_id=suggestion_id)


@router.post("/{suggestion_id}/reject", response_model=SuggestionResponse)
def reject(suggestion_id: uuid.UUID, body: SuggestionDecisionRequest,
           db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _ = body.confirm
    return service.reject(db, owner_id=current_user.id, suggestion_id=suggestion_id)
