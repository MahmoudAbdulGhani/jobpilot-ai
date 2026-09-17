import uuid
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.api.routes.auth import _require_bearer_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import clear_auth_cookies
from app.models import User
from app.services import account_data as service

router = APIRouter(prefix="/account/data", tags=["account data"])


class Password(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024, repr=False)


class DeleteRequest(Password):
    confirmation: str = Field(max_length=40)


class Receipt(BaseModel):
    receipt: str = Field(min_length=32, max_length=128, repr=False)


@router.post("/exports", status_code=201)
def export(body: Password, user: User = Depends(_require_bearer_user), db: Session = Depends(get_db)):
    return service.create_export(db, user.id, body.password, get_settings())


@router.get("/exports/{export_id}")
def download(export_id: uuid.UUID, user: User = Depends(_require_bearer_user), db: Session = Depends(get_db)):
    return Response(service.download(db, user, export_id), media_type="application/zip",
        headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="jobpilot-account.zip"'})


@router.post("/deletions", status_code=202)
def delete(body: DeleteRequest, response: Response, user: User = Depends(_require_bearer_user), db: Session = Depends(get_db)):
    result = service.request_deletion(db, user.id, body.password, body.confirmation)
    clear_auth_cookies(response)
    return result


@router.post("/deletions/{deletion_id}/status")
def status(deletion_id: uuid.UUID, body: Receipt, db: Session = Depends(get_db)):
    # Limited-purpose, high-entropy receipt: no account access and no personal data.
    return service.status(db, deletion_id, body.receipt)
