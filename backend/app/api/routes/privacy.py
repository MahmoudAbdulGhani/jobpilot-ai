"""Privacy controls: server-backed data-use matrix and consent toggles."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.privacy import ConsentChange, PrivacyMatrix
from app.services import privacy_service as service

router = APIRouter(prefix="/privacy", tags=["privacy"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


@router.get("/matrix", response_model=PrivacyMatrix)
def get_matrix(db: Database, current_user: CurrentUser, response: Response,
               settings: Annotated[Settings, Depends(get_settings)]):
    response.headers["Cache-Control"] = "no-store"
    return {"rows": service.matrix(db, current_user.id, settings)}


@router.patch("/consents", response_model=dict)
def set_consent(body: ConsentChange, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _ = body.confirm
    return service.set_consent(db, current_user.id, body.key, body.allowed)
