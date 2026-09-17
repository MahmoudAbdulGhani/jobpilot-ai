import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from app.api.routes.jobs import CurrentUser, Database
from app.core.config import get_settings
from app.models import ApplicationPack, ApplicationPackVersion, InterviewSession, InterviewOperation, Resume, ResumeExtraction
from app.schemas.interviews import InterviewSelection, InterviewStart, AnswerSave, Advance
from app.services import interview_service as service
from app.services.application_pack_service import PackError, owned_job

router = APIRouter(tags=["interview practice"])


def handle(operation):
    try:
        return operation()
    except PackError as error:
        raise HTTPException(error.status_code, error.message) from None


@router.get("/jobs/{job_id}/interviews/options")
def options(job_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    handle(lambda: owned_job(db, current_user.id, job_id))
    available, message = True, None
    try:
        config, _ = service.configuration(settings)
    except PackError as error:
        available, message = False, error.message
        config = {"provider": settings.JOBPILOT_INTERVIEW_PROVIDER, "model": settings.JOBPILOT_INTERVIEW_MODEL,
            "reasoning": settings.JOBPILOT_INTERVIEW_REASONING_EFFORT,
            "max_output_tokens": settings.JOBPILOT_INTERVIEW_MAX_OUTPUT_TOKENS}
    resumes = db.scalars(select(Resume).join(ResumeExtraction, ResumeExtraction.resume_id == Resume.id).where(
        Resume.owner_id == current_user.id, ResumeExtraction.reviewed_at.is_not(None),
        ResumeExtraction.status == "succeeded").order_by(Resume.created_at.desc(), Resume.id).limit(100))
    packs = db.execute(select(ApplicationPackVersion, ApplicationPack).join(ApplicationPack,
        ApplicationPackVersion.pack_id == ApplicationPack.id).where(ApplicationPack.owner_id == current_user.id,
        ApplicationPack.job_id == job_id, ApplicationPack.status == "ready", ApplicationPackVersion.approved_at.is_not(None))
        .order_by(ApplicationPackVersion.created_at.desc(), ApplicationPackVersion.id).limit(100))
    return {"available": available, "message": message, "configuration": config,
        "max_questions": min(6, settings.JOBPILOT_INTERVIEW_MAX_CALLS_PER_SESSION-1),
        "resumes": [{"id": r.id, "name": r.display_name} for r in resumes],
        "packs": [{"id": p.id, "version": v.number, "approved_at": v.approved_at} for v, p in packs]}


@router.post("/jobs/{job_id}/interviews/preview")
def preview(job_id: uuid.UUID, body: InterviewSelection, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.preview(db, current_user.id, job_id, body, settings))


@router.post("/jobs/{job_id}/interviews")
def start(job_id: uuid.UUID, body: InterviewStart, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(db, service.start(db, current_user.id, job_id, body, settings)))


@router.get("/jobs/{job_id}/interviews")
def listing(job_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response,
            after: uuid.UUID | None = None, limit: int = Query(10, ge=1, le=50)):
    response.headers["Cache-Control"] = "no-store"
    handle(lambda: owned_job(db, current_user.id, job_id))
    q = select(InterviewSession).where(InterviewSession.owner_id == current_user.id, InterviewSession.job_id == job_id)
    if after:
        q = q.where(InterviewSession.id > after)
    rows = list(db.scalars(q.order_by(InterviewSession.id).limit(limit+1)))
    return {"items": [{"id": r.id, "status": service.display_status(r, db.get(InterviewOperation, r.active_operation) if r.active_operation else None), "mode": r.mode, "question_count": r.question_count,
        "created_at": r.created_at} for r in rows[:limit]], "next_cursor": str(rows[limit-1].id) if len(rows)>limit else None}


@router.get("/interviews/{id}")
def get(id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(db, service.owned(db, current_user.id, id)))


@router.patch("/interviews/{id}/answer")
def save(id: uuid.UUID, body: AnswerSave, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(db, service.save_answer(db, current_user.id, id, body)))


@router.post("/interviews/{id}/advance")
def advance(id: uuid.UUID, body: Advance, db: Database, current_user: CurrentUser, response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    return handle(lambda: service.public(db, service.advance(db, current_user.id, id, body, settings)))


@router.delete("/interviews/{id}", status_code=204)
def delete(id: uuid.UUID, db: Database, current_user: CurrentUser):
    handle(lambda: service.delete(db, current_user.id, id))
    return Response(status_code=204)
