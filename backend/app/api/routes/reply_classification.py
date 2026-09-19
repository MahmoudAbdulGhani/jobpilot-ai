"""Reply classification: advisory only. Status changes need explicit confirmation."""
import uuid

from fastapi import APIRouter, Response

from app.api.routes.jobs import CurrentUser, Database
from app.schemas.reply_classification import ClassificationConfirmRequest, ClassificationResponse
from app.services import reply_classification_service as service

router = APIRouter(tags=["reply classification"])


@router.post("/replies/{reply_id}/classification", response_model=ClassificationResponse)
def classify(reply_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.classify(db, current_user.id, reply_id)


@router.get("/replies/{reply_id}/classification", response_model=ClassificationResponse | None)
def latest(reply_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.latest(db, current_user.id, reply_id)


@router.post("/replies/{reply_id}/classification/confirm", response_model=ClassificationResponse)
def confirm(reply_id: uuid.UUID, body: ClassificationConfirmRequest, db: Database,
            current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _ = body.confirm
    return service.confirm(db, current_user.id, reply_id, body.status)
