"""Public capabilities shared by API validation and the discovery UI."""
import re

SOURCES = {
    "jobtech": {
        "label": "JobTech JobSearch", "coverage": "Primarily Sweden; other countries may have few listings.",
        "filters": ["country", "region", "city", "remote"],
        "remote_accuracy": "approximate", "pagination": "offset",
        "ai_description": "when_supplied", "application": "source_link",
        "attribution_url": "https://jobsearch.api.jobtechdev.se/",
    },
    "jobicy": {
        "label": "Jobicy", "coverage": "Recent remote catalog only; eligibility is source-stated.",
        "filters": ["eligibility", "remote"],
        "remote_accuracy": "source_remote_catalog", "pagination": "cached_offset",
        "ai_description": "when_supplied", "application": "source_link",
        "attribution_url": "https://jobicy.com/jobs-rss-feed",
    },
    "jobopportunities": {
        "label": "Job Opportunities API", "coverage": "Worldwide first page, up to 50 results per search; refine filters to explore more.",
        "filters": ["country", "city", "us_state", "remote"],
        "remote_accuracy": "source_or_inferred", "pagination": "single_page",
        "ai_description": "when_supplied", "application": "employer_link_when_supplied",
        "attribution_url": "https://jobopportunitiesapi.org/",
    },
}


def validate(source, *, country="", region="", city="", eligibility="", offset=0):
    from app.services.discovery_provider import DiscoveryError
    if source not in SOURCES:
        raise DiscoveryError(422, "Unsupported discovery source.")
    if source == "jobicy" and (country or region or city):
        raise DiscoveryError(422, "Jobicy does not supply structured workplace geography; use applicant eligibility.")
    if source != "jobicy" and eligibility:
        raise DiscoveryError(422, "This source does not supply searchable applicant eligibility.")
    if source == "jobtech" and sum(bool(value) for value in (country, region, city)) > 1:
        raise DiscoveryError(422, "JobTech geography filters use source ranking when combined. Search one workplace place at a time.")
    if source == "jobopportunities" and (offset or (region and country.upper() != "US")):
        raise DiscoveryError(422, "Worldwide search has one page and state filtering is available only for the US.")
    if source == "jobopportunities" and ((country and not re.fullmatch(r"[A-Za-z]{2}", country))
            or (region and not re.fullmatch(r"[A-Za-z]{2}", region))):
        raise DiscoveryError(422, "Use a two-letter country or US state code for worldwide search.")
