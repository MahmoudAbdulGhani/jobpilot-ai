from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.routes.jobs import CurrentUser, Database
from app.core.config import get_settings
from app.schemas.discovery import (DiscoverySearch, DiscoveryPreview, DiscoveryImport,
    DiscoveryImported, ExternalId)
from app.services import discovery_provider, discovery_service

router = APIRouter(prefix="/discovery", tags=["discovery"])


def provider(settings=Depends(get_settings)):
    try:
        return discovery_provider.provider_for(settings)
    except discovery_provider.DiscoveryError as error:
        raise HTTPException(error.status, error.message) from None


@router.get("", response_model=DiscoverySearch)
def search(db: Database, current_user: CurrentUser,
    q: Annotated[str, Query(max_length=200)] = "",
    remote: bool = False, sort: Literal["relevance", "pubdate-desc"] = "relevance",
    offset: Annotated[int, Query(ge=0, le=1980)] = 0, source=Depends(provider)):
    try:
        jobs, total = source.search(q=q.strip(), remote=remote, sort=sort, offset=offset)
        next_offset = offset + discovery_provider.PAGE_SIZE
        return DiscoverySearch(items=discovery_service.with_duplicates(db, current_user.id, jobs),
            total=total, offset=offset,
            next_offset=next_offset if jobs and next_offset < min(total, 2000) else None)
    except discovery_provider.DiscoveryError as error:
        raise HTTPException(error.status, error.message) from None


@router.get("/{external_id}/preview", response_model=DiscoveryPreview)
def preview(external_id: ExternalId, db: Database, current_user: CurrentUser,
    response: Response, source=Depends(provider), settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return discovery_service.prepare_preview(db, current_user.id, source.preview(external_id), settings)
    except discovery_provider.DiscoveryError as error:
        raise HTTPException(error.status, error.message) from None


@router.post("/import", response_model=DiscoveryImported)
def import_job(body: DiscoveryImport, db: Database, current_user: CurrentUser,
    response: Response, settings=Depends(get_settings)):
    if not settings.JOBPILOT_DISCOVERY_ENABLED:
        raise HTTPException(503, "Job discovery is disabled.")
    try:
        job, duplicate = discovery_service.import_preview(db, current_user.id, body.preview_token, settings)
        response.status_code = 200 if duplicate else 201
        return DiscoveryImported(job=job, already_saved=duplicate)
    except discovery_provider.DiscoveryError as error:
        raise HTTPException(error.status, error.message) from None
