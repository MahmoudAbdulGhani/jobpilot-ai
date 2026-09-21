"""Daily digest: validated records only, preferences, preview-token gated delivery."""
from datetime import datetime, timezone
from datetime import timedelta
import pytest

from fastapi import status

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import DiscoveryCache, User
from app.services import digest_delivery

TEST_PASSWORD = "digest-test-password"


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def now():
    return datetime.now(timezone.utc)


def job_row(source, external_id, title):
    """One DiscoveryJob entry: jobicy HTTPS urls survive _valid_records."""
    return {"source": source, "external_id": external_id, "title": title,
            "company": "Example Co", "location": "Remote",
            "description": "Build things.",
            "source_url": f"https://jobicy.com/jobs/{external_id}",
            "published_at": "2026-09-10T00:00:00Z", "salary": None,
            "workplace_model": None, "applicant_region": "Unknown eligibility",
            "remote_arrangement": "remote", "test_data": True}


def payload_for(*jobs):
    """Digest-capable payload for one discovery row; source is the table PK,
    so several jobs share a single 'jobicy' row."""
    return {"jobs": [job_row(*job) for job in jobs],
            "checks": {job[1]: {"status": 200} for job in jobs}}


def jobicy_row(*jobs, refreshed_at=None):
    return DiscoveryCache(source="jobicy", payload=payload_for(*jobs),
                          refreshed_at=refreshed_at or now(), next_attempt_at=now())


def test_digest_preferences_and_validated_preview(client, db_session):
    owner = User(email="digest-first@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.add_all([
        jobicy_row(("jobicy", "ext-1", "Remote Engineer"), ("jobicy", "ext-2", "Local Engineer")),
        DiscoveryCache(source="jobtech", payload=payload_for(("jobtech", "ext-3", "Local Tech Engineer")),
                       refreshed_at=now(), next_attempt_at=now()),
        DiscoveryCache(source="digest-stale-1", payload=payload_for(("jobicy", "ext-4", "Stale Engineer")),
                       refreshed_at=datetime(2026, 9, 1, tzinfo=timezone.utc), next_attempt_at=now()),
        DiscoveryCache(source="digest-broken-1", payload={"source": "jobicy", "title": ""},
                       refreshed_at=now(), next_attempt_at=now()),
    ])
    db_session.commit()

    caller = api_client(client, db_session)
    try:
        prefs = caller.get("/api/digest/preferences", headers=auth(owner))
        assert prefs.status_code == status.HTTP_200_OK, prefs.text
        assert prefs.json()["cadence"] == "off", "digests default to off"

        changed = caller.put("/api/digest/preferences",
                             json={"cadence": "daily", "confirm": True}, headers=auth(owner))
        assert changed.json()["cadence"] == "daily"

        preview = caller.get("/api/digest/preview", headers=auth(owner))
        assert preview.status_code == status.HTTP_200_OK, preview.text
        body = preview.json()
        assert body["cadence"] == "daily"
        assert body["generated_at"]
        assert len(body["items"]) == 2, "only valid jobicy records are used"
        assert body["skipped_invalid"] == 3, "jobtech + stale + malformed rows are skipped"
        by_title = {item["title"]: item for item in body["items"]}
        assert by_title["Remote Engineer"]["source"] == "Jobicy"
        assert by_title["Local Engineer"]["source"] == "Jobicy"
        for item in body["items"]:
            assert item["source_url"], "attribution required"
            assert item["source_url"].startswith("https://jobicy.com/jobs/"), "jobicy HTTPS attribution required"
            assert item["published_at"], "timestamps required"
            assert item["test_data"] is True, "synthetic markers stay visible"
        assert body["delivery"] == {"enabled": False,
                                    "reason": "Digest email delivery is disabled; previews are in-app only."}
        assert body["preview_token"], "sending is gated on a preview token"

        bad = caller.put("/api/digest/preferences",
                         json={"cadence": "hourly", "confirm": True}, headers=auth(owner))
        assert bad.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, bad.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)
        db_session.rollback()


def test_digest_send_rejects_disabled_transport(client, db_session):
    owner = User(email="digest-send@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    caller = api_client(client, db_session)
    try:
        token = caller.get("/api/digest/preview", headers=auth(owner)).json()["preview_token"]
        response = caller.post("/api/digest/send", json={"confirm": True, "preview_token": token},
                               headers=auth(owner))
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE, response.text
        assert "disabled" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.pop(get_db, None)
        db_session.rollback()


def test_digest_send_via_test_transport_marks_last_sent(client, db_session):
    digest_delivery.test_messages.clear()
    owner = User(email="digest-sent@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.add(jobicy_row(("jobicy", "ext-sent", "Sent Engineer")))
    db_session.commit()

    test_settings = get_settings().model_copy(update={
        "JOBPILOT_DIGEST_MAIL_TRANSPORT": "test",
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = api_client(client, db_session)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        token = caller.get("/api/digest/preview", headers=auth(owner)).json()["preview_token"]
        response = caller.post("/api/digest/send", json={"confirm": True, "preview_token": token},
                               headers=auth(owner))
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["items"] == 1
        assert body["recipient"] == owner.email
        assert body["transport"] == "test"
        assert body["sent_at"]
        assert body["delivery"] == {"enabled": True,
                                    "reason": "Test transport (end-to-end test mode) delivers to the in-memory sink."}

        prefs = caller.get("/api/digest/preferences", headers=auth(owner)).json()
        assert prefs["last_sent_at"], "the send marks the preference row"
        sink = digest_delivery.test_messages.get(owner.email, "")
        assert "Sent Engineer" in sink and "validated listing" in sink
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)
        digest_delivery.test_messages.clear()
        db_session.rollback()


def test_digest_send_requires_matching_recent_preview_token(client, db_session):
    digest_delivery.test_messages.clear()
    owner = User(email="digest-token@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    other = User(email="digest-token-other@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add_all([owner, other])
    db_session.commit()
    db_session.refresh(owner)
    db_session.add(jobicy_row(("jobicy", "ext-a", "Token Engineer")))
    db_session.commit()

    test_settings = get_settings().model_copy(update={
        "JOBPILOT_DIGEST_MAIL_TRANSPORT": "test",
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = api_client(client, db_session)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        token = caller.get("/api/digest/preview", headers=auth(owner)).json()["preview_token"]

        malformed = caller.post("/api/digest/send", json={"confirm": True, "preview_token": "garbage"},
                                headers=auth(owner))
        assert malformed.status_code == status.HTTP_409_CONFLICT, malformed.text

        foreign_token = caller.get("/api/digest/preview", headers=auth(other)).json()["preview_token"]
        foreign = caller.post("/api/digest/send", json={"confirm": True, "preview_token": foreign_token},
                              headers=auth(owner))
        assert foreign.status_code == status.HTTP_409_CONFLICT, foreign.text

        digest_row = db_session.get(DiscoveryCache, "jobicy")
        digest_row.payload = payload_for(("jobicy", "ext-a", "Token Engineer"),
                                         ("jobicy", "ext-b", "Second Engineer"))
        db_session.commit()
        stale = caller.post("/api/digest/send", json={"confirm": True, "preview_token": token},
                            headers=auth(owner))
        assert stale.status_code == status.HTTP_409_CONFLICT, stale.text

        current = caller.get("/api/digest/preview", headers=auth(owner)).json()["preview_token"]
        sent = caller.post("/api/digest/send", json={"confirm": True, "preview_token": current},
                           headers=auth(owner))
        assert sent.status_code == status.HTTP_200_OK, sent.text
        assert sent.json()["items"] == 2

        again = caller.post("/api/digest/send", json={"confirm": True, "preview_token": current},
                            headers=auth(owner))
        assert again.status_code == status.HTTP_409_CONFLICT, "a used/last_sent digest token is stale"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)
        digest_delivery.test_messages.clear()
        db_session.rollback()


def test_digest_send_receipt_importable_and_constructible():
    """Regression: DigestDelivery must be defined before DigestSendReceipt."""
    from datetime import datetime, timezone
    from app.schemas.digest import DigestSendReceipt, DigestDelivery

    receipt = DigestSendReceipt(
        sent_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        recipient="test@example.com",
        items=3,
        transport="smtp",
        delivery=DigestDelivery(enabled=True, reason="ok"),
    )
    assert receipt.transport == "smtp"
    assert receipt.delivery.enabled is True
    assert receipt.delivery.reason == "ok"


@pytest.mark.parametrize("condition", ["stale", "future", "expired", "gone", "unavailable", "bad-deadline"])
def test_catalog_freshness_and_expiry(db_session, condition):
    from app.services import digest_service
    row = jobicy_row(("jobicy", "expiry", "Engineer"))
    if condition == "stale": row.refreshed_at = now() - timedelta(hours=2)
    if condition == "future": row.refreshed_at = now() + timedelta(hours=2)
    if condition == "expired": row.payload["jobs"][0]["deadline"] = (now() - timedelta(seconds=1)).isoformat()
    if condition == "bad-deadline": row.payload["jobs"][0]["deadline"] = "invalid"
    if condition in {"gone", "unavailable"}: row.payload["checks"]["expiry"]["status"] = 410 if condition == "gone" else 503
    db_session.add(row); db_session.commit()
    valid, skipped = digest_service._valid_records(db_session, get_settings())
    assert valid == [] and skipped == 1


def test_real_catalog_shape_with_empty_checks_is_consumed(db_session):
    from app.services import digest_service
    from app.services.discovery_catalog import JobicyCatalog
    from app.schemas.discovery import DiscoveryJob
    class MockJobicy:
        def catalog(self): return [DiscoveryJob.model_validate(job_row("jobicy", "real-shape", "Engineer"))]
    JobicyCatalog(db_session, MockJobicy()).load()
    valid, skipped = digest_service._valid_records(db_session, get_settings())
    assert len(valid) == 1 and skipped == 0


@pytest.mark.parametrize("change", ["expired-token", "recipient", "transport", "expired-catalog"])
def test_changed_or_expired_review_never_sends(db_session, monkeypatch, change):
    import jwt
    import uuid
    from fastapi import HTTPException
    from unittest.mock import Mock
    from app.services import digest_service
    owner = User(email=f"digest-{uuid.uuid4()}@example.test", password_hash="unused")
    row = jobicy_row(("jobicy", "review", "Engineer"))
    db_session.add_all([owner, row]); db_session.commit()
    settings = get_settings()
    token = digest_service.preview(db_session, owner.id, settings)["preview_token"]
    if change == "expired-token":
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        payload["exp"] = now() - timedelta(seconds=1)
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    if change == "recipient": owner.email = f"changed-{uuid.uuid4()}@example.test"
    if change == "transport": settings = settings.model_copy(update={"JOBPILOT_DIGEST_MAIL_TRANSPORT": "smtp"})
    if change == "expired-catalog": row.refreshed_at = now() - timedelta(hours=2)
    db_session.commit()
    send = Mock(side_effect=AssertionError("Unapproved email"))
    monkeypatch.setattr(digest_delivery, "send", send)
    with pytest.raises(HTTPException) as error:
        digest_service.send(db_session, owner.id, settings, token)
    assert error.value.status_code == 409
    send.assert_not_called()
