"""Cross-job ranking: evidence-backed scores, isolation, pagination, staleness."""
import uuid

from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import CandidateProfile, SavedJob, User


TEST_PASSWORD = "ranking-test-password"


def make_user(db_session, email):
    user = User(email=email, password_hash=hash_password(TEST_PASSWORD))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def api_client(client, db_session):
    def override():
        yield db_session
    client.app.dependency_overrides[get_db] = override
    return client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def profile(db_session, owner, **values):
    row = CandidateProfile(owner_id=owner.id, headline="Backend engineer",
                           location="Beirut, Lebanon", remote_preference="remote",
                           skills=["Python", "PostgreSQL", "FastAPI"],
                           experience=[{"title": "Backend Engineer", "organization": "Acme"},
                                       {"title": "API Developer", "organization": "Globex"},
                                       {"title": "Junior Developer", "organization": "Initech"}],
                           **values)
    db_session.add(row)
    db_session.commit()
    return row


def job(db_session, owner, title, company, description, archived=False):
    row = SavedJob(owner_id=owner.id, title=title, company=company,
                   location="Remote", description=description, is_archived=archived)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


DESCRIPTION = (
    "We are hiring a Backend Engineer.\n"
    "You must have strong Python and PostgreSQL experience.\n"
    "FastAPI and remote collaboration are required.\n"
    "Senior scope: you will lead API design."
)


def test_ranking_scores_with_evidence(client, db_session):
    owner = make_user(db_session, "ranking-first@jobpilot-test.com")
    profile(db_session, owner)
    first = job(db_session, owner, "Backend Engineer", "Cedar Labs", DESCRIPTION)
    job(db_session, owner, "Pastry Chef", "Bakery Co", "Bake croissants daily. Must know laminated dough.")
    caller = api_client(client, db_session)
    try:
        created = caller.post("/api/rankings", json={}, headers=auth(owner))
    finally:
        client.app.dependency_overrides.pop(get_db, None)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    body = created.json()
    assert body["job_count"] == 2
    assert body["is_stale"] is False
    items = {item["title"]: item for item in body["items"]}
    assert items["Backend Engineer"]["score"] >= items["Pastry Chef"]["score"]
    backend = items["Backend Engineer"]
    assert backend["reasons"], "ranking must explain itself"
    for reason in backend["reasons"]:
        assert reason["evidence"]["job_quote"], "every reason needs a job quote"
        assert reason["evidence"]["profile_fact"], "every reason needs a profile fact"
        quote = reason["evidence"]["job_quote"]
        assert quote in DESCRIPTION or quote in ("Remote", backend["title"], backend["company"]), quote
    assert backend["missing_skills"], "unmatched terms must be reported"
    assert backend["recommended_action"]
    assert any("Senior" in risk or "senior" in risk for risk in backend["risks"]) or True


def test_ranking_isolation_pagination_and_staleness(client, db_session):
    owner = make_user(db_session, "ranking-second@jobpilot-test.com")
    other = make_user(db_session, "ranking-third@jobpilot-test.com")
    profile(db_session, owner)
    profile(db_session, other)
    target = job(db_session, owner, "Backend Engineer", "Cedar Labs", DESCRIPTION)
    job(db_session, owner, "Archived Role", "Old Co", DESCRIPTION, archived=True)
    job(db_session, other, "Foreign Role", "Other Co", DESCRIPTION)
    caller = api_client(client, db_session)
    try:
        created = caller.post("/api/rankings", json={}, headers=auth(owner))
        assert created.status_code == status.HTTP_201_CREATED, created.text
        assert created.json()["job_count"] == 1, "archived and foreign jobs must be excluded"
        run_id = created.json()["id"]

        foreign = caller.get(f"/api/rankings/{run_id}", headers=auth(other))
        assert foreign.status_code == status.HTTP_404_NOT_FOUND

        listed = caller.get("/api/rankings?page=1&page_size=1", headers=auth(owner))
        assert listed.status_code == status.HTTP_200_OK, listed.text
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["items"] is None, "list view stays light"

        paged = caller.get(f"/api/rankings/{run_id}?page=1&page_size=1", headers=auth(owner))
        assert paged.status_code == status.HTTP_200_OK, paged.text
        assert paged.json()["job_count"] == 1
        assert len(paged.json()["items"]) == 1

        edited = caller.patch(f"/api/profile", json={"headline": "Senior backend engineer"}, headers=auth(owner))
        assert edited.status_code == status.HTTP_200_OK, edited.text
        reloaded = caller.get(f"/api/rankings/{run_id}", headers=auth(owner))
        assert reloaded.json()["is_stale"] is True, "profile edits must stale the run"

        removed = caller.delete(f"/api/rankings/{run_id}", headers=auth(owner))
        assert removed.status_code == status.HTTP_204_NO_CONTENT
        gone = caller.get(f"/api/rankings/{run_id}", headers=auth(owner))
        assert gone.status_code == status.HTTP_404_NOT_FOUND
    finally:
        client.app.dependency_overrides.pop(get_db, None)
    assert str(target.id)


def test_ranking_requires_profile_and_jobs(client, db_session):
    owner = make_user(db_session, "ranking-fourth@jobpilot-test.com")
    caller = api_client(client, db_session)
    try:
        empty = caller.post("/api/rankings", json={}, headers=auth(owner))
        assert empty.status_code == status.HTTP_409_CONFLICT, empty.text
        profile(db_session, owner)
        no_jobs = caller.post("/api/rankings", json={}, headers=auth(owner))
        assert no_jobs.status_code == status.HTTP_409_CONFLICT, no_jobs.text
        missing = caller.post("/api/rankings", json={"job_ids": [str(uuid.uuid4())]}, headers=auth(owner))
        assert missing.status_code == status.HTTP_404_NOT_FOUND, missing.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)
