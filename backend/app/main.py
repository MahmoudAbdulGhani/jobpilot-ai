from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.application_packs import router as application_packs_router
from app.api.routes.auth import router as auth_router
from app.api.routes.e2e import router as e2e_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.job_fit import router as job_fit_router
from app.api.routes.profile import router as profile_router
from app.api.routes.profile_suggestions import router as profile_suggestions_router
from app.api.routes.resumes import router as resumes_router
from app.core.config import get_settings


def create_application() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )
    application.include_router(health_router, prefix=settings.API_PREFIX)
    application.include_router(auth_router, prefix=settings.API_PREFIX)
    application.include_router(jobs_router, prefix=settings.API_PREFIX)
    application.include_router(job_fit_router, prefix=settings.API_PREFIX)
    application.include_router(profile_router, prefix=settings.API_PREFIX)
    application.include_router(
        profile_suggestions_router, prefix=settings.API_PREFIX)
    application.include_router(resumes_router, prefix=settings.API_PREFIX)
    application.include_router(
        application_packs_router, prefix=settings.API_PREFIX)
    application.include_router(e2e_router, prefix=settings.API_PREFIX)
    return application


app = create_application()
