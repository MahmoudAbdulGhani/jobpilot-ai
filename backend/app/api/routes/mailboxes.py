import uuid
import logging
from typing import Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.routes.jobs import CurrentUser, Database
from app.core.config import get_settings
from app.models import MailboxConnection
from app.services import mailbox_service as service
from app.services.mailbox_provider import MailboxError, provider_for, validate_configuration

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])
COOKIE = "jobpilot_mailbox_oauth"
COOKIE_PATH = "/api/mailboxes/oauth/callback"


class MailboxAccessLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            values = list(record.args)
            if isinstance(values[2], str) and values[2].split("?", 1)[0] == COOKIE_PATH:
                values[2] = COOKIE_PATH
                record.args = tuple(values)
        return True


def protect_access_logs():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, MailboxAccessLogFilter) for f in logger.filters):
        logger.addFilter(MailboxAccessLogFilter())


class OAuthStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capabilities: list[Literal["send", "read_replies"]] = Field(default_factory=list, max_length=2)
    connection_id: uuid.UUID | None = None


class ScrubMailboxCallback:
    """Strip authorization codes/state from ASGI access logs before routing."""
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == COOKIE_PATH:
            raw = scope.get("query_string", b"")
            scope["query_string"] = b""
            try: scope["mailbox_callback"] = parse_qs(raw.decode("ascii", errors="ignore"), max_num_fields=20) if len(raw)<16384 else {}
            except ValueError: scope["mailbox_callback"] = {}
        await self.app(scope, receive, send)


@router.get("")
def connections(db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    try: provider_for(settings); available = True
    except MailboxError: available = False
    return {"available":available, "test_provider":settings.JOBPILOT_MAILBOX_TEST_PROVIDER,
        "items":[service.public(r) for r in db.scalars(select(MailboxConnection).where(MailboxConnection.owner_id == current_user.id))]}


@router.post("/oauth/start")
def start(body: OAuthStart, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    try:
        provider = provider_for(settings)
        url, browser = service.start(db, current_user.id, body.capabilities, body.connection_id, settings, provider)
    except MailboxError as error: raise HTTPException(error.status, error.code) from None
    response.set_cookie(COOKIE, browser, max_age=600, httponly=True, secure=settings.JOBPILOT_GOOGLE_REDIRECT_URI.startswith("https://"),
        samesite="lax", path=COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    return {"authorization_url":url}


@router.get("/oauth/callback")
def callback(request: Request, db: Database, settings=Depends(get_settings)):
    try: validate_configuration(settings)
    except MailboxError: raise HTTPException(503, "not_configured") from None
    query = request.scope.get("mailbox_callback", {})
    def one(name):
        values = query.get(name, [])
        return values[0] if len(values)==1 else None
    try:
        provider = provider_for(settings)
        outcome = service.finish(db, one("state"), request.cookies.get(COOKIE), one("code"),
            bool(one("error")), settings, provider)
    except MailboxError as error:
        db.rollback()
        outcome = error.code
    # Trusted, configured URL only; no user-provided return/redirect parameter.
    if not settings.JOBPILOT_MAILBOX_SETTINGS_URL:
        raise HTTPException(503, "not_configured")
    response = RedirectResponse(settings.JOBPILOT_MAILBOX_SETTINGS_URL + "?mailbox=" + outcome, status_code=303)
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/{connection_id}/check")
def check(connection_id: uuid.UUID, db: Database, current_user: CurrentUser, settings=Depends(get_settings)):
    try: return service.check(db, current_user.id, connection_id, settings, provider_for(settings))
    except MailboxError as error: raise HTTPException(error.status, error.code) from None


@router.post("/{connection_id}/disconnect")
def disconnect(connection_id: uuid.UUID, db: Database, current_user: CurrentUser, settings=Depends(get_settings)):
    try: provider = provider_for(settings)
    except MailboxError: provider = None
    try: return service.disconnect(db, current_user.id, connection_id, settings, provider)
    except MailboxError as error: raise HTTPException(error.status, error.code) from None
