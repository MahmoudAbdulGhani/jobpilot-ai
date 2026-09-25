import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.routes.jobs import CurrentUser, Database
from app.core.config import get_settings
from app.schemas.discovery import (DiscoverySearch, DiscoveryPreview, DiscoveryImport,
    DiscoveryImported, ExternalId)
from app.schemas.jobs import SavedJobResponse
from app.services import discovery_provider, discovery_service, discovery_sources

router = APIRouter(prefix="/discovery", tags=["discovery"])


def provider(db: Database, source: Literal['jobtech','jobicy','jobopportunities']='jobtech', settings=Depends(get_settings)):
    try:
        return discovery_provider.provider_for(settings, source, db)
    except discovery_provider.DiscoveryError as error:
        raise HTTPException(error.status, error.message) from None


@router.get("/sources")
def sources(current_user: CurrentUser):
    return {"sources": discovery_sources.SOURCES}


@router.get("", response_model=DiscoverySearch)
def search(request: Request, db: Database, current_user: CurrentUser,
    q: Annotated[str, Query(max_length=200)] = "",
    location: Annotated[str, Query(max_length=100)] = "",
    country: Annotated[str, Query(max_length=100)] = "",
    region: Annotated[str, Query(max_length=100)] = "",
    city: Annotated[str, Query(max_length=100)] = "",
    eligibility: Annotated[str, Query(max_length=100)] = "",
    remote: bool = False, sort: Literal["relevance", "pubdate-desc"] = "relevance",
    offset: Annotated[int, Query(ge=0, le=1980)] = 0, source=Depends(provider)):
    try:
        source_name = request.query_params.get("source", "jobtech")
        country, region, city, eligibility = (value.strip() for value in (country, region, city, eligibility))
        if location and eligibility:
            raise discovery_provider.DiscoveryError(422, "Use only one applicant eligibility field.")
        eligibility = eligibility or location.strip()
        discovery_sources.validate(source_name, country=country, region=region, city=city,
            eligibility=eligibility, offset=offset)
        filters = ({"location": eligibility} if source_name == "jobicy" else
            {"country": country, "region": region, "city": city})
        jobs, total = source.search(q=q.strip(), remote=remote, sort=sort, offset=offset, **filters)
        next_offset = offset + discovery_provider.PAGE_SIZE
        return DiscoverySearch(items=discovery_service.with_duplicates(db, current_user.id, jobs),
            total=total, offset=offset,
            next_offset=next_offset if source_name != "jobopportunities" and jobs and next_offset < min(total, 2000) else None,
            result_limit=50 if source_name == "jobopportunities" else None)
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


@router.post("/saved/{job_id}/refresh-description", response_model=SavedJobResponse)
def refresh_description(job_id: uuid.UUID, db: Database, current_user: CurrentUser,
    response: Response, settings=Depends(get_settings)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return discovery_service.refresh_missing_description(db, current_user.id, job_id, settings)
    except discovery_provider.DiscoveryError as error:
        raise HTTPException(error.status, error.message) from None
