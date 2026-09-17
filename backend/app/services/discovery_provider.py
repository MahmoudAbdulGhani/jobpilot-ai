"""JobTech adapter: fixed documented endpoints, bounded I/O, no persistence."""
import json
import re

import httpx
from pydantic import ValidationError

from app.schemas.discovery import DiscoveryJob

BASE_URL = "https://jobsearch.api.jobtechdev.se"
PAGE_SIZE = 20
MAX_RESPONSE_BYTES = 2_000_000


class DiscoveryError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid source text")
    return value.strip() or None


def parse_job(raw):
    """Prefer the documented plain-text description; never render provider HTML."""
    try:
        if raw.get("removed") is True:
            raise DiscoveryError(410, "This source listing is no longer available.")
        external_id = raw["id"]
        if not isinstance(external_id, str) or not re.fullmatch(r"[0-9A-Za-z_-]{1,128}", external_id):
            raise ValueError("Invalid source ID")
        address = raw.get("workplace_address") or {}
        location = list(dict.fromkeys(filter(None, [optional_text(address.get(k)) for k in ("municipality", "region", "country")])))
        return DiscoveryJob(
            external_id=external_id, title=raw["headline"], company=raw["employer"]["name"],
            location=", ".join(location) or None,
            description=optional_text((raw.get("description") or {}).get("text")),
            # Canonical source link, never an application URL supplied in the ad.
            source_url=f"https://arbetsformedlingen.se/platsbanken/annonser/{external_id}",
            published_at=raw.get("publication_date"), deadline=raw.get("application_deadline"),
            salary=optional_text(raw.get("salary_description")),
            workplace_model=optional_text((raw.get("workplace_model") or {}).get("label")),
        )
    except (KeyError, TypeError, AttributeError, ValueError, ValidationError):
        raise DiscoveryError(502, "The source returned a listing with invalid or oversized fields.") from None


class JobTechProvider:
    def __init__(self, transport=None):
        self.transport = transport

    def _get(self, path, params=None):
        try:
            with httpx.Client(timeout=8, follow_redirects=False, transport=self.transport) as client:
                with client.stream("GET", BASE_URL + path, params=params, headers={"Accept": "application/json"}) as response:
                    if response.status_code == 429:
                        raise DiscoveryError(429, "JobTech's rate limit was reached. Wait before searching again.")
                    if response.status_code in (404, 410):
                        raise DiscoveryError(410, "This source listing is no longer available.")
                    if response.status_code != 200:
                        raise DiscoveryError(503, "JobTech is unavailable. Please try later.")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise DiscoveryError(502, "The source response exceeds the safe size limit.")
                    return json.loads(content)
        except httpx.HTTPError:
            raise DiscoveryError(503, "JobTech could not be reached. Please try later.") from None
        except (ValueError, UnicodeError):
            raise DiscoveryError(502, "JobTech returned an invalid response.") from None

    def search(self, *, q, remote, sort, offset):
        params = {"q": q, "sort": sort, "offset": offset, "limit": PAGE_SIZE, "resdet": "full"}
        if remote:
            params["remote"] = "true"
        raw = self._get("/search", params)
        try:
            hits, total = raw["hits"], raw["total"]["value"]
            if not isinstance(hits, list) or len(hits) > PAGE_SIZE or type(total) is not int or total < 0:
                raise ValueError()
            return [parse_job(hit) for hit in hits], total
        except (KeyError, TypeError, ValueError):
            raise DiscoveryError(502, "JobTech returned invalid search results.") from None

    def preview(self, external_id):
        if not re.fullmatch(r"[0-9A-Za-z_-]{1,128}", external_id):
            raise DiscoveryError(422, "Invalid source ID.")
        job = parse_job(self._get(f"/ad/{external_id}"))
        if job.external_id != external_id:
            raise DiscoveryError(502, "The source returned a different listing.")
        return job


class SyntheticJobTechProvider:
    """Explicitly labeled fixture for guarded local browser tests only."""
    def preview(self, external_id):
        if external_id != "synthetic-100":
            raise DiscoveryError(410, "This source listing is no longer available.")
        job = parse_job({"id": external_id, "headline": "Synthetic Backend Engineer",
            "employer": {"name": "Synthetic Nordic Demo"},
            "description": {"text": "Build Python APIs and PostgreSQL services. <script>unsafe()</script>"},
            "workplace_address": {"municipality": "Stockholm", "country": "Sweden"},
            "publication_date": "2026-09-17T08:00:00", "application_deadline": "2026-10-31T23:59:59"})
        return job.model_copy(update={"test_data": True})

    def search(self, *, q, remote, sort, offset):
        if q == "rate-limit":
            raise DiscoveryError(429, "JobTech's rate limit was reached. Wait before searching again.")
        if q == "unavailable":
            raise DiscoveryError(503, "JobTech is unavailable. Please try later.")
        return ([], 0) if q == "empty" or offset else ([self.preview("synthetic-100")], 1)


def provider_for(settings):
    if not settings.JOBPILOT_DISCOVERY_ENABLED:
        raise DiscoveryError(503, "Job discovery is disabled.")
    if settings.JOBPILOT_DISCOVERY_TEST_PROVIDER:
        if not settings.E2E_TEST_MODE or settings.POSTGRES_DB != settings.POSTGRES_TEST_DB:
            raise DiscoveryError(503, "The discovery test provider is restricted to guarded tests.")
        return SyntheticJobTechProvider()
    return JobTechProvider()
