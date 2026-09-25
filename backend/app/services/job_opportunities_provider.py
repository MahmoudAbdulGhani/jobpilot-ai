"""Bounded, keyless Job Opportunities API adapter. No arbitrary provider URLs are fetched."""
import ipaddress
import json
import uuid
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.schemas.discovery import DiscoveryJob
from app.services.discovery_provider import DiscoveryError

BASE = "https://api.jobopportunitiesapi.org"
MAX_RESPONSE_BYTES = 2_000_000


def safe_link(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if url.scheme != "https" or not host or url.username or url.password or url.port or host.lower() == "localhost" or host.endswith(".localhost"):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value
    except ValueError:
        return None


def parse_job(raw):
    try:
        identifier = str(uuid.UUID(raw["id"]))
        application = safe_link(raw.get("apply_url"))
        if not application or raw.get("status", "live") != "live":
            raise ValueError()
        def optional(key):
            value = raw.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError()
            return value.strip() or None if isinstance(value, str) else None
        country, state, city = optional("country"), optional("state"), optional("city")
        remote = raw.get("remote")
        if remote not in (None, "remote", "hybrid", "on_site", "not_stated"):
            raise ValueError()
        if type(raw.get("remote_inferred", False)) is not bool:
            raise ValueError()
        description = optional("description")
        salary = optional("salary_display")
        return DiscoveryJob(source="jobopportunities", external_id=identifier,
            title=raw["title"], company=raw["company"], location=optional("location"),
            workplace_country=country, workplace_region=state, workplace_city=city,
            description=description, source_url=application, apply_url=application,
            upstream_source=optional("source"), published_at=raw.get("posted_at"),
            salary=salary, workplace_model=remote.replace("_", " ") if remote else None,
            remote_arrangement="remote" if remote == "remote" else "unknown",
            remote_inferred=raw.get("remote_inferred", False) if remote == "remote" else False)
    except (KeyError, TypeError, ValueError, ValidationError):
        raise DiscoveryError(502, "The worldwide source returned an invalid listing.") from None


class JobOpportunitiesProvider:
    def __init__(self, transport=None):
        self.transport = transport

    def _get(self, path, params=None):
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False, transport=self.transport) as client:
                with client.stream("GET", BASE + path, params=params, headers={"Accept": "application/json"}) as response:
                    if response.status_code == 429:
                        raise DiscoveryError(429, "Worldwide search is rate limited. Try again shortly.")
                    if response.status_code == 404:
                        raise DiscoveryError(410, "This worldwide listing is no longer available.")
                    if response.status_code != 200:
                        raise DiscoveryError(503, "Worldwide search is unavailable. Try again later.")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE_BYTES:
                            raise DiscoveryError(502, "Worldwide source response exceeded the safe size limit.")
                    return json.loads(data)
        except httpx.HTTPError:
            raise DiscoveryError(503, "Worldwide search could not be reached.") from None
        except (ValueError, UnicodeError):
            raise DiscoveryError(502, "Worldwide source returned an invalid response.") from None

    def search(self, *, q, remote, sort, offset, country="", region="", city="", **_):
        if offset:
            raise DiscoveryError(422, "Worldwide search offers one page; refine your filters.")
        params = {"limit": 50}
        if q: params["q"] = q
        if country: params["country"] = country.upper()
        if region: params["state"] = region.upper()
        if city: params["city"] = city
        if remote: params.update(remote="remote", remote_confirmed="true")
        raw = self._get("/public/jobs", params)
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), list) or len(raw["data"]) > 50:
            raise DiscoveryError(502, "Worldwide source returned invalid search results.")
        jobs = []
        seen = set()
        for row in raw["data"]:
            try:
                job = parse_job(row)
            except DiscoveryError:
                continue  # One unsafe or incomplete listing must not hide the other results.
            if job.external_id not in seen:
                jobs.append(job)
                seen.add(job.external_id)
        return jobs, len(jobs)

    def preview(self, external_id):
        try: identifier = str(uuid.UUID(external_id))
        except ValueError: raise DiscoveryError(422, "Invalid worldwide listing ID.") from None
        raw = self._get("/public/jobs/" + identifier)
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), dict):
            raise DiscoveryError(502, "Worldwide source returned an invalid listing.")
        job = parse_job(raw["data"])
        if job.external_id != identifier:
            raise DiscoveryError(502, "Worldwide source returned a different listing.")
        return job


class SyntheticJobOpportunitiesProvider:
    def preview(self, external_id):
        identifier = "12345678-1234-4234-8234-123456789abc"
        if external_id != identifier: raise DiscoveryError(410, "Synthetic vacancy unavailable.")
        return parse_job({"id": identifier, "title": "Synthetic Global Engineer", "company": "Demo Global",
            "location": "New York, US", "country": "US", "state": "NY", "city": "New York", "remote": "remote",
            "remote_inferred": False, "description": "Build Python APIs; Java preferred.",
            "apply_url": "https://employer.example/jobs/global-engineer", "source": "greenhouse"}).model_copy(update={"test_data": True})

    def search(self, *, q, remote, sort, offset, country="", region="", city="", **_):
        job = self.preview("12345678-1234-4234-8234-123456789abc")
        if offset or (country and country.upper() != "US") or (region and region.upper() != "NY") or (city and city.casefold() not in "new york"):
            return [], 0
        return [job], 1
