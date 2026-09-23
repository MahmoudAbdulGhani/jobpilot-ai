import uuid

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import CandidateProfile, User

TEST_PASSWORD = "profile-test-password"


@pytest.fixture()
def profile_users(db_session):
    first = User(
        email="profile-first@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    second = User(
        email="profile-second@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    return first, second


@pytest.fixture()
def profile_client(client, db_session):
    def override():
        yield db_session

    client.app.dependency_overrides[get_db] = override
    yield client
    client.app.dependency_overrides.pop(get_db, None)


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def full_profile_body(**overrides):
    body = {
        "headline": "Senior Backend Engineer focused on reliable APIs",
        "target_roles": ["Backend Engineer", "Platform Engineer"],
        "location": "Beirut, Lebanon",
        "remote_preference": "hybrid",
        "work_authorization": "needs_sponsorship",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience": [
            {
                "title": "Backend Engineer",
                "organization": "Example Systems",
                "period": "2022 — present",
                "notes": "Built and maintained public APIs.",
            }
        ],
        "education": [
            {
                "school": "State University",
                "degree": "B.Sc.",
                "field": "Computer Science",
                "period": "2016 — 2020",
            }
        ],
        "languages": [{"name": "English", "proficiency": "professional"}],
        "salary_preference": {"currency": "USD", "min": 120_000, "max": 160_000},
    }
    body.update(overrides)
    return body


READABLE_FIELDS = (
    "headline",
    "target_roles",
    "location",
    "remote_preference",
    "work_authorization",
    "skills",
    "experience",
    "education",
    "languages",
    "salary_preference",
)


def test_get_and_patch_require_authentication(client):
    assert client.get("/api/profile").status_code == status.HTTP_401_UNAUTHORIZED
    assert (
        client.patch("/api/profile", json={}).status_code
        == status.HTTP_401_UNAUTHORIZED
    )


def test_get_without_profile_is_404(profile_client, profile_users):
    owner, _ = profile_users
    response = profile_client.get("/api/profile", headers=auth_headers(owner))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Profile not found"}


def test_patch_creates_then_persists_profile(profile_client, profile_users, db_session):
    owner, _ = profile_users
    created = profile_client.patch(
        "/api/profile", json=full_profile_body(), headers=auth_headers(owner)
    )
    assert created.status_code == status.HTTP_200_OK
    profile = created.json()
    assert profile["owner_id"] == str(owner.id)
    assert profile["headline"].startswith("Senior Backend Engineer")
    assert profile["target_roles"] == ["Backend Engineer", "Platform Engineer"]
    assert profile["remote_preference"] == "hybrid"
    assert profile["work_authorization"] == "needs_sponsorship"
    assert profile["skills"] == ["Python", "FastAPI", "PostgreSQL"]
    assert profile["experience"][0]["organization"] == "Example Systems"
    assert profile["education"][0]["field"] == "Computer Science"
    assert profile["languages"][0]["proficiency"] == "professional"
    assert profile["salary_preference"] == {
        "currency": "USD",
        "min": 120_000,
        "max": 160_000,
    }
    assert profile["created_at"]

    stored = db_session.scalar(
        select(CandidateProfile).where(CandidateProfile.owner_id == owner.id)
    )
    assert stored is not None
    assert stored.skills == ["Python", "FastAPI", "PostgreSQL"]
    assert stored.experience == profile["experience"]
    assert stored.education == profile["education"]
    assert stored.languages == profile["languages"]

    retrieved = profile_client.get("/api/profile", headers=auth_headers(owner))
    assert retrieved.status_code == status.HTTP_200_OK
    assert retrieved.json() == profile
    assert retrieved.json()["skills"] == stored.skills
    assert retrieved.json()["experience"] == stored.experience
    assert retrieved.json()["education"] == stored.education
    assert retrieved.json()["languages"] == stored.languages


def test_patch_is_partial_and_upserts(profile_client, profile_users):
    owner, _ = profile_users
    created = profile_client.patch(
        "/api/profile", json=full_profile_body(), headers=auth_headers(owner)
    ).json()

    updated = profile_client.patch(
        "/api/profile",
        json={"headline": "Staff Backend Engineer"},
        headers=auth_headers(owner),
    )
    assert updated.status_code == status.HTTP_200_OK
    body = updated.json()
    assert body["headline"] == "Staff Backend Engineer"
    for field in READABLE_FIELDS:
        if field != "headline":
            assert body[field] == created[field]
    assert body["id"] == created["id"]
    assert body["created_at"] == created["created_at"]


def test_patch_round_trips_manual_target_roles_experience_and_authorization(profile_client, profile_users):
    owner, _ = profile_users
    payload = {
        "headline": "Remote",
        "location": "Tripoli, Lebanon",
        "target_roles": ["Product Engineer"],
        "skills": ["Python"],
        "experience": [{"title": "Product Engineer", "organization": "Cedar Labs", "period": "2020-2024", "notes": None}],
        "education": [{"school": "State University", "degree": "BSc", "field": "Computer Science", "period": "2020"}],
        "languages": [{"name": "English", "proficiency": "professional"}],
        "remote_preference": "remote",
        "work_authorization": "citizen",
        "salary_preference": {"currency": "USD", "min": 70000, "max": 90000},
    }
    saved = profile_client.patch("/api/profile", json=payload, headers=auth_headers(owner))
    assert saved.status_code == status.HTTP_200_OK
    assert saved.json()["target_roles"] == ["Product Engineer"]
    assert saved.json()["experience"][0]["organization"] == "Cedar Labs"
    assert saved.json()["work_authorization"] == "citizen"
    reloaded = profile_client.get("/api/profile", headers=auth_headers(owner))
    assert reloaded.status_code == status.HTTP_200_OK
    assert reloaded.json()["headline"] == "Remote"
    assert reloaded.json()["location"] == "Tripoli, Lebanon"
    assert reloaded.json()["target_roles"] == ["Product Engineer"]
    assert reloaded.json()["experience"][0]["title"] == "Product Engineer"
    assert reloaded.json()["work_authorization"] == "citizen"


def test_patch_can_clear_fields_with_null(profile_client, profile_users):
    owner, _ = profile_users
    body = full_profile_body()
    body["salary_preference"] = None
    created = profile_client.patch(
        "/api/profile", json=body, headers=auth_headers(owner)
    )
    assert created.status_code == status.HTTP_200_OK
    assert created.json()["salary_preference"] is None

    cleared = profile_client.patch(
        "/api/profile",
        json={"headline": None, "skills": None, "languages": None},
        headers=auth_headers(owner),
    )
    assert cleared.status_code == status.HTTP_200_OK
    result = cleared.json()
    assert result["headline"] is None
    assert result["skills"] is None
    assert result["languages"] is None
    assert result["remote_preference"] == body["remote_preference"]


def test_empty_patch_creates_blank_profile(profile_client, profile_users, db_session):
    owner, _ = profile_users
    response = profile_client.patch(
        "/api/profile", json={}, headers=auth_headers(owner)
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    for field in READABLE_FIELDS:
        assert body[field] is None
    assert body["owner_id"] == str(owner.id)
    assert db_session.scalar(
        select(CandidateProfile).where(CandidateProfile.owner_id == owner.id)
    ) is not None


def test_cross_user_isolation(profile_client, profile_users, db_session):
    first, second = profile_users
    first_profile = profile_client.patch(
        "/api/profile", json=full_profile_body(), headers=auth_headers(first)
    )
    assert first_profile.status_code == status.HTTP_200_OK

    assert (
        profile_client.get("/api/profile", headers=auth_headers(second)).status_code
        == status.HTTP_404_NOT_FOUND
    )

    second_profile = profile_client.patch(
        "/api/profile",
        json={"headline": "Second user headline", "location": "Remote"},
        headers=auth_headers(second),
    )
    assert second_profile.status_code == status.HTTP_200_OK
    assert second_profile.json()["owner_id"] == str(second.id)
    assert second_profile.json()["id"] != first_profile.json()["id"]

    refreshed_first = profile_client.get(
        "/api/profile", headers=auth_headers(first)
    ).json()
    assert refreshed_first["id"] == first_profile.json()["id"]
    assert refreshed_first["headline"].startswith("Senior Backend Engineer")

    rows = list(db_session.scalars(select(CandidateProfile)))
    assert len(rows) == 2
    assert {str(row.owner_id) for row in rows} == {str(first.id), str(second.id)}


def test_server_owned_fields_cannot_be_set_by_client(profile_client, profile_users):
    owner, other = profile_users
    response = profile_client.patch(
        "/api/profile",
        json={
            "headline": "Role",
            "owner_id": str(other.id),
            "id": str(uuid.uuid4()),
            "created_at": "2026-01-01T00:00:00Z",
        },
        headers=auth_headers(owner),
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    "body",
    [
        {"headline": "x" * 201},
        {"remote_preference": "sometimes"},
        {"work_authorization": "none"},
        {"remote_preference": "Remote"},
        {"work_authorization": "H1B"},
        {"location": "x" * 301},
        {"target_roles": [""]},
        {"target_roles": ["   "]},
        {"target_roles": ["x" * 201]},
        {"skills": [""]},
        {"skills": ["x" * 101]},
        {"salary_preference": {"currency": "USD", "min": 200_000, "max": 100_000}},
        {"salary_preference": {"min": -1}},
        {"experience": [{"title": "Role", "organization": "Org", "notes": "x" * 2_001}]},
        {"experience": [{"title": "Role", "organization": ""}]},
        {"education": [{"school": "", "degree": "B.Sc."}]},
        {"languages": [{"name": "English", "proficiency": "fluent"}]},
        {"target_roles": "Backend Engineer"},
        {"skills": 42},
    ],
)
def test_patch_validation(profile_client, profile_users, body):
    owner, _ = profile_users
    response = profile_client.patch(
        "/api/profile", json=body, headers=auth_headers(owner)
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_normalization_trims_and_blank_lists_are_rejected(profile_client, profile_users):
    owner, _ = profile_users
    response = profile_client.patch(
        "/api/profile",
        json={
            "headline": "  Senior Engineer  ",
            "location": "  Remote  ",
            "skills": [" Python ", "SQL"],
        },
        headers=auth_headers(owner),
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["headline"] == "Senior Engineer"
    assert body["location"] == "Remote"
    assert body["skills"] == ["Python", "SQL"]

    cleared = profile_client.patch(
        "/api/profile", json={"headline": "   "}, headers=auth_headers(owner)
    )
    assert cleared.status_code == status.HTTP_200_OK
    assert cleared.json()["headline"] is None

    empty_list = profile_client.patch(
        "/api/profile", json={"target_roles": []}, headers=auth_headers(owner)
    )
    assert empty_list.status_code == status.HTTP_200_OK
    assert empty_list.json()["target_roles"] == []
