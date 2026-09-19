"""Read-only customer Q&A. GET and SELECT only; no writes by construction."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.qa import QaAnswer, QaEntity
from app.services import qa_service as service

router = APIRouter(prefix="/qa", tags=["customer Q&A"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get("/ask", response_model=QaAnswer)
def ask(entity: QaEntity, q: Annotated[str, Query(max_length=500)], db: Database,
        current_user: CurrentUser, response: Response,
        limit: Annotated[int, Query(ge=1, le=20)] = 10):
    response.headers["Cache-Control"] = "no-store"
    return service.ask(db, current_user.id, entity, q, limit)
