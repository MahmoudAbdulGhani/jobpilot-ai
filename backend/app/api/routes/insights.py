"""Unified insights: owner-scoped, read-only, redacted summaries."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.insights import InsightsResponse
from app.services import insights_service as service

router = APIRouter(prefix="/insights", tags=["insights"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=InsightsResponse)
def get_insights(db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.build(db, current_user.id)
