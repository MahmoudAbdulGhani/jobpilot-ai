"""Shared short-lived worldwide search cache and conservative public API rate guard."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.models.discovery_cache import DiscoveryCache
from app.schemas.discovery import DiscoveryJob
from app.services.discovery_provider import DiscoveryError
from app.services.job_opportunities_provider import JobOpportunitiesProvider


def now():
    return datetime.now(timezone.utc)


class JobOpportunitiesCatalog:
    def __init__(self, db, provider=None):
        self.db, self.provider = db, provider or JobOpportunitiesProvider()

    def _guard(self):
        db = self.db
        db.execute(insert(DiscoveryCache).values(source="joa-rate", payload={"count": 0}, next_attempt_at=now()).on_conflict_do_nothing())
        row = db.scalar(select(DiscoveryCache).where(DiscoveryCache.source == "joa-rate").with_for_update())
        if row.next_attempt_at <= now():
            row.next_attempt_at = now() + timedelta(minutes=1)
            row.payload = {"count": 0}
        count = row.payload.get("count", 0)
        if count >= 35:
            db.commit()
            raise DiscoveryError(429, "Worldwide search is busy. Try again in a minute.")
        row.payload = {"count": count + 1}
        db.commit()  # Durable allowance claim before transport.

    def _cleanup(self):
        self.db.execute(delete(DiscoveryCache).where(DiscoveryCache.source.like("joa-%"),
            DiscoveryCache.source != "joa-rate", DiscoveryCache.next_attempt_at < now() - timedelta(hours=1)))
        self.db.commit()

    def _cached(self, kind, identifier, fetch, ttl):
        db = self.db
        key = "joa-" + kind + ":" + hashlib.sha256(identifier.encode()).hexdigest()[:20]
        db.execute(insert(DiscoveryCache).values(source=key, payload={}, next_attempt_at=now()).on_conflict_do_nothing())
        row = db.scalar(select(DiscoveryCache).where(DiscoveryCache.source == key).with_for_update())
        if row.next_attempt_at > now():
            payload = row.payload
            db.commit()
            if "error" in payload:
                raise DiscoveryError(payload["error"], "Worldwide source is unavailable for this query. Try again later.")
            if payload:
                return payload["value"]
            raise DiscoveryError(503, "Worldwide source request is pending. Try again shortly.")
        row.next_attempt_at = now() + ttl
        row.payload = {}
        db.commit()
        try:
            self._guard()
            value = fetch()
        except DiscoveryError as error:
            row = db.get(DiscoveryCache, key, populate_existing=True)
            row.payload = {"error": error.status}
            db.commit()
            self._cleanup()
            raise
        row = db.get(DiscoveryCache, key, populate_existing=True)
        row.payload = {"value": value}
        row.refreshed_at = now()
        db.commit()
        # The cache is bounded by time, not by the number of filter combinations ever searched.
        self._cleanup()
        return value

    def search(self, **filters):
        key = json.dumps(filters, sort_keys=True, separators=(",", ":"))
        def fetch():
            jobs, _ = self.provider.search(**filters)
            return [job.model_dump(mode="json") for job in jobs]
        # A new cache namespace avoids serving earlier search rows without text.
        value = self._cached("q2", key, fetch, timedelta(minutes=5))
        jobs = [DiscoveryJob.model_validate(raw) for raw in value]
        return jobs, len(jobs)

    def preview(self, external_id):
        value = self._cached("ad", external_id, lambda: self.provider.preview(external_id).model_dump(mode="json"), timedelta(minutes=10))
        return DiscoveryJob.model_validate(value)
