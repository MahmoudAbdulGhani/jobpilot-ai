from typing import Annotated
from fastapi import APIRouter, Depends, Response
from app.api.routes.jobs import CurrentUser, Database
from app.core.config import Settings, get_settings
from app.services.entitlements import snapshot

router = APIRouter(prefix="/account/usage", tags=["usage"])


@router.get("")
def usage(user: CurrentUser, db: Database, response: Response, settings: Annotated[Settings, Depends(get_settings)]):
    response.headers["Cache-Control"] = "no-store"
    return snapshot(db, user.id, settings)
