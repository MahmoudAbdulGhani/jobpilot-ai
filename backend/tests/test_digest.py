"""Daily digest: validated records only, preferences, gated delivery adapter."""
from datetime import datetime, timezone

from fastapi import status

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import DiscoveryCache, User
from app.services import digest_delivery

TEST_PASSWORD = "digest-test-password"
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def valid_payload(source, external_id, title):
    return {"source": source, "external_id": external_id, "title": title,
            "company": "Example Co", "location": "Remote",
            "description": "Build things.",
            "source_url": "https://example.com/jobs/1",
            "published_at": "2026-09-10T00:00:00Z", "salary": None,
            "workplace_model": None, "applicant_region": "Unknown eligibility",
            "remote_arrangement": "remote", "test_data": True}


def test_digest_preferences_and_validated_preview(client, db_session):
    owner = User(email="digest-first@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.add_all([
        DiscoveryCache(source="digest-jobicy-1", payload=valid_payload("jobicy", "ext-1", "Remote Engineer"),
                       refreshed_at=NOW, next_attempt_at=NOW),
        DiscoveryCache(source="digest-jobtech-1", payload=valid_payload("jobtech", "ext-2", "Local Engineer"),
                       refreshed_at=NOW, next_attempt_at=NOW),
        DiscoveryCache(source="digest-broken-1", payload={"source": "jobicy", "title": ""},
                       refreshed_at=NOW, next_attempt_at=NOW),
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
        assert len(body["items"]) == 2, "only validated records are used"
        assert body["skipped_invalid"] == 1
        by_title = {item["title"]: item for item in body["items"]}
        assert by_title["Remote Engineer"]["source"] == "Jobicy"
        assert by_title["Local Engineer"]["source"] == "JobTech JobSearch"
        for item in body["items"]:
            assert item["source_url"] and item["published_at"], "attribution and timestamps required"
            assert item["test_data"] is True, "synthetic markers stay visible"
        assert body["delivery"] == {"enabled": False,
                                    "reason": "Digest email delivery is disabled; previews are in-app only."}

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
        response = caller.post("/api/digest/send", json={"confirm": True}, headers=auth(owner))
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
    db_session.add(DiscoveryCache(source="digest-jobicy-sent",
                                  payload=valid_payload("jobicy", "ext-sent", "Sent Engineer"),
                                  refreshed_at=NOW, next_attempt_at=NOW))
    db_session.commit()

    test_settings = get_settings().model_copy(update={
        "JOBPILOT_DIGEST_MAIL_TRANSPORT": "test",
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = api_client(client, db_session)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        response = caller.post("/api/digest/send", json={"confirm": True}, headers=auth(owner))
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
