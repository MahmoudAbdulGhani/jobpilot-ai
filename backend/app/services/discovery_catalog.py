"""Shared hourly public cache, separate from the provider and owned saved jobs."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.discovery_cache import DiscoveryCache
from app.schemas.discovery import DiscoveryJob
from app.services.discovery_provider import DiscoveryError, PAGE_SIZE
from app.services.jobicy_provider import JobicyProvider


def now(): return datetime.now(timezone.utc)


class JobicyCatalog:
    def __init__(self, db, provider=None): self.db, self.provider = db, provider or JobicyProvider()

    def load(self):
        db = self.db
        # A single global row bounds cache space and refreshes across web workers.
        db.execute(insert(DiscoveryCache).values(source='jobicy',payload={},next_attempt_at=now()).on_conflict_do_nothing())
        row = db.scalar(select(DiscoveryCache).where(DiscoveryCache.source=='jobicy').with_for_update().execution_options(populate_existing=True))
        if row.next_attempt_at > now():
            payload, fresh = row.payload, row.refreshed_at and row.refreshed_at > now()-timedelta(hours=1)
            db.commit()
            if not fresh: raise DiscoveryError(payload.get('error_status',503), 'Jobicy cache is unavailable; the next attempt is limited to once per hour.')
            return payload
        row.next_attempt_at = now()+timedelta(hours=1)
        row.payload = {}; row.refreshed_at = None
        db.commit()  # Durable attempt claim: failures/restarts cannot cause polling bursts.
        try: jobs = self.provider.catalog()
        except DiscoveryError as error:
            row = db.get(DiscoveryCache, 'jobicy', populate_existing=True)
            row.payload = {'error_status':error.status}; db.commit()
            raise
        row = db.get(DiscoveryCache, 'jobicy', populate_existing=True)
        row.payload = {'jobs':[job.model_dump(mode='json') for job in jobs], 'checks':{}}
        row.refreshed_at = now(); db.commit()
        return row.payload

    def search(self, *, q, remote, sort, offset, location=''):
        payload = self.load()
        jobs = [DiscoveryJob.model_validate(raw) for raw in payload['jobs']]
        # These are explicitly local filters on actual cached text, not invented API slugs.
        jobs = [j for j in jobs if q.casefold() in (j.title+' '+j.company+' '+(j.description or '')).casefold()
                and location.casefold() in (j.applicant_region or '').casefold()
                and payload.get('checks',{}).get(j.external_id,{}).get('status') != 410]
        if sort == 'pubdate-desc': jobs.sort(key=lambda j:j.published_at or '',reverse=True)
        return jobs[offset:offset+PAGE_SIZE], len(jobs)

    def preview(self, external_id):
        self.load()
        db = self.db
        row = db.scalar(select(DiscoveryCache).where(DiscoveryCache.source=='jobicy').with_for_update().execution_options(populate_existing=True))
        payload = dict(row.payload); checks = dict(payload.get('checks',{}))
        raw = next((j for j in payload.get('jobs',[]) if j['external_id']==external_id),None)
        if not raw: raise DiscoveryError(410, 'This listing is outside the current Jobicy catalog. Search again; absence does not prove expiry.')
        job = DiscoveryJob.model_validate(raw)
        checked = checks.get(external_id)
        if checked:
            db.commit()
            if checked['status'] != 200: raise DiscoveryError(checked['status'], 'Jobicy availability could not be confirmed; listing may be expired or provider unavailable.')
            return job
        # At most 20 explicit availability checks per hourly catalog, shared by all users.
        if len(checks) >= 20: raise DiscoveryError(429, 'Jobicy preview-check allowance reached. Try after the hourly refresh.')
        checks[external_id] = {'status':503}; payload['checks'] = checks
        row.payload = payload; db.commit()  # Claim before I/O; interrupted HEAD is not retried.
        status = 200
        try: self.provider.check(job)
        except DiscoveryError as error: status = error.status
        row = db.scalar(select(DiscoveryCache).where(DiscoveryCache.source=='jobicy').with_for_update().execution_options(populate_existing=True))
        updated = dict(row.payload); checks = dict(updated.get('checks',{}))
        # Do not insert a stale check into a replaced catalog.
        if external_id in checks:
            checks[external_id] = {'status':status}; updated['checks'] = checks; row.payload = updated
            db.commit()
        if status != 200: raise DiscoveryError(status, 'Jobicy availability could not be confirmed; listing may be expired or provider unavailable.')
        return job
