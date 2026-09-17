import asyncio
import uuid
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from app.api.routes.jobs import CurrentUser, Database
from app.api.routes.interviews import handle
from app.core.config import Settings, get_settings
from app.schemas.interviews import Strict
from app.services import interview_service, interview_voice as service
from app.services.application_pack_service import PackError

router = APIRouter(prefix="/interviews/{session_id}/voice", tags=["interview-voice"])
Config = Annotated[Settings, Depends(get_settings)]


class Speak(Strict):
    request_key: uuid.UUID
    question_number: int = Field(ge=1, le=6)
    consent: Literal[True]


@router.get("/options")
def options(session_id: uuid.UUID, user: CurrentUser, db: Database, settings: Config, response: Response):
    response.headers["Cache-Control"] = "no-store"
    handle(lambda: interview_service.owned(db, user.id, session_id))
    try: return {"available": True, **service.configuration(settings)}
    except PackError as error: return {"available": False, "message": error.message}


@router.post("/transcribe")
async def transcribe(session_id: uuid.UUID, user: CurrentUser, db: Database, settings: Config,
                     request: Request, response: Response, request_key: uuid.UUID,
                     question_number: Annotated[int, Query(ge=1, le=6)], consent: bool = False):
    response.headers["Cache-Control"] = "no-store"
    handle(lambda: interview_service.owned(db, user.id, session_id))
    handle(lambda: service.configuration(settings))
    if consent is not True: raise HTTPException(422, "Explicit external speech-processing consent is required")
    limit = 44 + settings.JOBPILOT_VOICE_MAX_SECONDS * 32000
    # Read raw bytes rather than UploadFile: no multipart spooling to disk.
    audio = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                if len(audio)+len(chunk) > limit: raise HTTPException(413, "Recording exceeds the configured limit")
                audio.extend(chunk)
        return await run_in_threadpool(handle, lambda: service.run(db, user.id, session_id,
            request_key, question_number, consent, "transcribe", settings, bytes(audio)))
    except TimeoutError:
        raise HTTPException(408, "Recording upload interrupted; your text answer is unchanged") from None
    finally:
        audio.clear()


@router.post("/speak")
def speak(session_id: uuid.UUID, body: Speak, user: CurrentUser, db: Database, settings: Config, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.run(db, user.id, session_id, body.request_key,
        body.question_number, body.consent, "speak", settings))
