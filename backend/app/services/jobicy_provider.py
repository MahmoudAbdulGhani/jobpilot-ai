"""Jobicy public API. Fixed endpoints, plain text, no saved-job persistence."""
import json
import math
import re
import time
from html import unescape
from html.parser import HTMLParser
import httpx
from app.schemas.discovery import DiscoveryJob
from app.services.discovery_provider import DiscoveryError, MAX_RESPONSE_BYTES, PAGE_SIZE

BASE = "https://jobicy.com"
CATALOG_LIMIT = 100


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "iframe"}: self.hidden += 1
        if not self.hidden and tag in {"p", "div", "li", "br", "h1", "h2", "h3"}: self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "iframe"}: self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {"p", "div", "li", "h1", "h2", "h3"}: self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def plain(value):
    if value is None or value == "": return None
    if not isinstance(value, str) or len(value) > 100_000: raise ValueError()
    parser = PlainText(); parser.feed(value)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip()) or None


def valid_url(url, identifier):
    # Never accept a caller URL, query, port, userinfo, encoded path or redirect.
    return isinstance(url, str) and re.fullmatch(r"https://jobicy\.com/jobs/" + re.escape(identifier) + r"-[a-zA-Z0-9_-]+/?", url) is not None


def parse_job(raw):
    try:
        if type(raw['id']) is not int or raw['id'] <= 0: raise ValueError()
        identifier = str(raw['id'])
        if not valid_url(raw['url'], identifier): raise ValueError()
        salary = None
        low, high = raw.get('salaryMin'), raw.get('salaryMax')
        if low is not None or high is not None:
            for value in (low, high):
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value < 0): raise ValueError()
            if low is not None and high is not None and low > high: raise ValueError()
            currency, period = raw.get('salaryCurrency'), raw.get('salaryPeriod')
            if currency is not None and not isinstance(currency,str): raise ValueError()
            if period is not None and not isinstance(period,str): raise ValueError()
            salary = f"{currency or 'Currency not supplied'}: {low if low is not None else '?'}–{high if high is not None else '?'} / {period or 'period not supplied'}"
        region = plain(raw.get('jobGeo'))
        if region and region.casefold() in {'unknown', 'n/a', 'not specified'}: region = None
        return DiscoveryJob(source='jobicy', external_id=identifier, title=unescape(raw['jobTitle']),
            company=unescape(raw['companyName']), description=plain(raw.get('jobDescription')),
            source_url=raw['url'], published_at=raw.get('pubDate'), salary=salary,
            workplace_model='Remote (Jobicy listing)', remote_arrangement='remote', applicant_region=region)
    except (KeyError, TypeError, AttributeError, ValueError):
        raise DiscoveryError(502, 'Jobicy returned a malformed or oversized listing.') from None


class JobicyProvider:
    def __init__(self, transport=None): self.transport = transport

    def _request(self, method, path, params=None):
        try:
            with httpx.Client(timeout=8, follow_redirects=False, trust_env=False, transport=self.transport) as client:
                started = time.monotonic()
                with client.stream(method, BASE + path, params=params, headers={'Accept':'application/json'}) as response:
                    if response.status_code == 429: raise DiscoveryError(429, 'Jobicy rate limit reached. Try again after the hourly cache refresh.')
                    if response.status_code in (404,410): raise DiscoveryError(410, 'This Jobicy vacancy has expired or been removed.')
                    if response.status_code != 200: raise DiscoveryError(503, 'Jobicy is unavailable. Please try later.')
                    if method == 'HEAD': return None
                    content = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES or time.monotonic() - started > 15:
                            raise DiscoveryError(502, 'Jobicy response exceeded the safe resource limit.')
                    return json.loads(content)
        except httpx.HTTPError:
            raise DiscoveryError(503, 'Jobicy could not be reached. Please try later.') from None
        except (ValueError, UnicodeError):
            raise DiscoveryError(502, 'Jobicy returned an invalid response.') from None

    def catalog(self, count=CATALOG_LIMIT):
        if not 1 <= count <= CATALOG_LIMIT: raise ValueError('Invalid catalog size')
        raw = self._request('GET', '/api/v2/remote-jobs', {'count':count})
        if not isinstance(raw,dict) or not isinstance(raw.get('jobs'),list) or len(raw['jobs']) > count:
            raise DiscoveryError(502, 'Jobicy returned invalid catalog data.')
        jobs = [parse_job(row) for row in raw['jobs']]
        if len({row.external_id for row in jobs}) != len(jobs): raise DiscoveryError(502, 'Jobicy returned repeated listing identifiers.')
        return jobs

    def check(self, job):
        if job.source != 'jobicy' or not valid_url(job.source_url, job.external_id):
            raise DiscoveryError(422, 'Invalid Jobicy source identity.')
        self._request('HEAD', job.source_url[len(BASE):])


class SyntheticJobicyProvider:
    def preview(self, external_id):
        if external_id != '123456': raise DiscoveryError(410, 'Synthetic vacancy unavailable.')
        return parse_job({'id':123456,'url':'https://jobicy.com/jobs/123456-synthetic-backend-engineer',
            'jobTitle':'Synthetic Backend Engineer','companyName':'Synthetic Nordic Demo',
            'jobGeo':'EMEA','pubDate':'2026-09-17T08:00:00Z',
            'jobDescription':'<p>Build Python APIs. Employer must confirm eligible countries.</p><script>unsafe()</script>'}).model_copy(update={'test_data':True})

    def search(self, *, q, remote, sort, offset, location=''):
        if q == 'rate-limit': raise DiscoveryError(429, 'Jobicy rate limit reached.')
        if q == 'unavailable': raise DiscoveryError(503, 'Jobicy unavailable.')
        if q == 'empty' or offset or (location and location.casefold() not in 'emea'): return [],0
        return [self.preview('123456')],1
