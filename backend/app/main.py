from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from app.api.routes.accounts import router as accounts_router
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.operations import RequestSafety
from app.services.object_store import StorageUnavailable

from app.api.routes.application_packs import router as application_packs_router
from app.api.routes.application_tracking import router as application_tracking_router
from app.api.routes.application_tracking import router_global as application_tracking_global_router
from app.api.routes.auth import router as auth_router
from app.api.routes.e2e import router as e2e_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.discovery import router as discovery_router
from app.api.routes.mailboxes import router as mailboxes_router, ScrubMailboxCallback, protect_access_logs
from app.api.routes.email_applications import router as email_applications_router
from app.api.routes.interviews import router as interviews_router
from app.api.routes.reminders import router as reminders_router
from app.api.routes.replies import router as replies_router
from app.api.routes.job_fit import router as job_fit_router
from app.api.routes.profile import router as profile_router
from app.api.routes.profile_suggestions import router as profile_suggestions_router
from app.api.routes.resumes import router as resumes_router
from app.core.config import get_settings


def create_application() -> FastAPI:
    protect_access_logs()
    settings = get_settings()
    application = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        docs_url=None if settings.ENVIRONMENT == "production" else "/api/docs",
        openapi_url=None if settings.ENVIRONMENT == "production" else "/api/openapi.json",
    )
    @application.exception_handler(RequestValidationError)
    async def safe_account_validation(request, error):
        if settings.ENVIRONMENT == "production" or request.url.path.startswith(settings.API_PREFIX + "/account/"):
            return JSONResponse(status_code=422, content={"detail": [
                {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                for item in error.errors()]})
        return await request_validation_exception_handler(request, error)
    @application.exception_handler(StorageUnavailable)
    async def unavailable_storage(request, error):
        return JSONResponse(status_code=503, content={"detail":"Private document storage is unavailable; try again later"})
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
        expose_headers=["X-Request-ID"],
    )
    application.include_router(health_router, prefix=settings.API_PREFIX)
    application.include_router(auth_router, prefix=settings.API_PREFIX)
    application.include_router(accounts_router, prefix=settings.API_PREFIX)
    application.include_router(jobs_router, prefix=settings.API_PREFIX)
    application.include_router(discovery_router, prefix=settings.API_PREFIX)
    application.include_router(mailboxes_router, prefix=settings.API_PREFIX)
    application.include_router(email_applications_router, prefix=settings.API_PREFIX)
    application.include_router(replies_router, prefix=settings.API_PREFIX)
    application.include_router(reminders_router, prefix=settings.API_PREFIX)
    application.include_router(interviews_router, prefix=settings.API_PREFIX)
    application.add_middleware(ScrubMailboxCallback)
    application.include_router(job_fit_router, prefix=settings.API_PREFIX)
    application.include_router(profile_router, prefix=settings.API_PREFIX)
    application.include_router(
        profile_suggestions_router, prefix=settings.API_PREFIX)
    application.include_router(resumes_router, prefix=settings.API_PREFIX)
    application.include_router(
        application_packs_router, prefix=settings.API_PREFIX)
    application.include_router(
        application_tracking_router, prefix=settings.API_PREFIX)
    application.include_router(
        application_tracking_global_router, prefix=settings.API_PREFIX)
    application.include_router(e2e_router, prefix=settings.API_PREFIX)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS, www_redirect=False)
    application.add_middleware(RequestSafety)
    return application


app = create_application()
