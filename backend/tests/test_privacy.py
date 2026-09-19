"""Privacy matrix: least-privilege defaults, server-backed consent state."""
from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import User

TEST_PASSWORD = "privacy-test-password"


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_matrix_defaults_and_toggle(client, db_session):
    owner = User(email="privacy-first@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    caller = api_client(client, db_session)
    try:
        matrix = caller.get("/api/privacy/matrix", headers=auth(owner))
        assert matrix.status_code == status.HTTP_200_OK, matrix.text
        rows = {row["domain"]: row for row in matrix.json()["rows"]}
        assert set(rows) == {"profile", "confirmed CV text", "selected job", "pack drafts",
                             "mailbox data", "advisory outputs"}
        for row in rows.values():
            assert row["fields_used"] and row["used_for"] and row["provider"] and row["retention"]
            assert isinstance(row["allowed"], bool)
        # Least privilege: optional AI uses default to denied.
        assert rows["confirmed CV text"]["allowed"] is False
        assert rows["selected job"]["allowed"] is False
        assert rows["pack drafts"]["allowed"] is False
        # Core storage is required and shown allowed.
        assert rows["profile"]["required"] is True and rows["profile"]["allowed"] is True

        changed = caller.patch("/api/privacy/consents",
                               json={"key": "ai_job_fit", "allowed": True, "confirm": True},
                               headers=auth(owner))
        assert changed.status_code == status.HTTP_200_OK, changed.text
        assert changed.json() == {"key": "ai_job_fit", "allowed": True,
                                  "detail": "Saved job description and profile facts sent to the AI provider for fit analysis."}
        reloaded = caller.get("/api/privacy/matrix", headers=auth(owner))
        selected = {row["domain"]: row for row in reloaded.json()["rows"]}["selected job"]
        assert selected["allowed"] is True, "consent state persists server-side"

        # Required and unknown uses are not toggleable.
        refused = caller.patch("/api/privacy/consents",
                               json={"key": "profile", "allowed": False, "confirm": True},
                               headers=auth(owner))
        assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, refused.text
        unknown = caller.patch("/api/privacy/consents",
                               json={"key": "nope", "allowed": True, "confirm": True},
                               headers=auth(owner))
        assert unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, unknown.text
        sloppy = caller.patch("/api/privacy/consents",
                              json={"key": "ai_job_fit", "allowed": True},
                              headers=auth(owner))
        assert sloppy.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, sloppy.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)
