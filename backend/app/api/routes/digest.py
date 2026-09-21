"""Daily digest: validated records, preferences, explicit delivery adapter."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.models import User
from app.schemas.digest import DigestCadenceChange, DigestPreferences, DigestPreview, DigestSendReceipt, DigestSendRequest
from app.services import digest_service as service

router = APIRouter(prefix="/digest", tags=["digest"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/preferences", response_model=DigestPreferences)
def get_preferences(db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.preferences(db, current_user.id)


@router.put("/preferences", response_model=DigestPreferences)
def set_preferences(body: DigestCadenceChange, db: Database,
                    current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _ = body.confirm
    return service.set_cadence(db, current_user.id, body.cadence)


@router.get("/preview", response_model=DigestPreview)
def get_preview(db: Database, current_user: CurrentUser, settings: SettingsDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.preview(db, current_user.id, settings)


@router.post("/send", response_model=DigestSendReceipt)
def send_digest(body: DigestSendRequest, db: Database, current_user: CurrentUser,
                settings: SettingsDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _ = body.confirm
    return service.send(db, current_user.id, settings, body.preview_token)
