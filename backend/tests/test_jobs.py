import uuid

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import SavedJob, User

TEST_PASSWORD = "saved-job-test-password"


@pytest.fixture()
def job_users(db_session):
    first = User(
        email="jobs-first@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    second = User(
        email="jobs-second@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    return first, second


@pytest.fixture()
def jobs_client(client, db_session):
    def override():
        yield db_session

    client.app.dependency_overrides[get_db] = override
    yield client
    client.app.dependency_overrides.pop(get_db, None)


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def create_job(client, user: User, **overrides):
    body = {"title": "Backend Engineer", "company": "Example Systems"}
    body.update(overrides)
    return client.post("/api/jobs", json=body, headers=auth_headers(user))


def test_complete_saved_job_workflow(jobs_client, job_users):
    owner, _ = job_users
    created = create_job(
        jobs_client,
        owner,
        location="Beirut, Lebanon",
        description="Build reliable APIs.",
        source_url="https://careers.example.com/jobs/backend-1",
        notes="Ask about the platform team.",
    )

    assert created.status_code == status.HTTP_201_CREATED
    job = created.json()
    assert job["owner_id"] == str(owner.id)
    assert job["title"] == "Backend Engineer"
    assert job["is_archived"] is False
    assert job["created_at"]
    assert job["updated_at"]

    listed = jobs_client.get("/api/jobs", headers=auth_headers(owner))
    assert listed.status_code == status.HTTP_200_OK
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == job["id"]

    retrieved = jobs_client.get(
        f"/api/jobs/{job['id']}", headers=auth_headers(owner)
    )
    assert retrieved.status_code == status.HTTP_200_OK
    assert retrieved.json() == job

    updated = jobs_client.patch(
        f"/api/jobs/{job['id']}",
        json={"title": "Senior Backend Engineer", "notes": None, "is_archived": True},
        headers=auth_headers(owner),
    )
    assert updated.status_code == status.HTTP_200_OK
    assert updated.json()["title"] == "Senior Backend Engineer"
    assert updated.json()["notes"] is None
    assert updated.json()["company"] == "Example Systems"
    assert updated.json()["is_archived"] is True

    active = jobs_client.get("/api/jobs", headers=auth_headers(owner)).json()
    archived = jobs_client.get(
        "/api/jobs?archived=true", headers=auth_headers(owner)
    ).json()
    assert active["total"] == 0
    assert archived["total"] == 1

    deleted = jobs_client.delete(
        f"/api/jobs/{job['id']}", headers=auth_headers(owner)
    )
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert deleted.content == b""
    assert (
        jobs_client.get(f"/api/jobs/{job['id']}", headers=auth_headers(owner)).status_code
        == status.HTTP_404_NOT_FOUND
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/jobs", {"title": "Role", "company": "Company"}),
        ("get", "/api/jobs", None),
        ("get", f"/api/jobs/{uuid.uuid4()}", None),
        ("patch", f"/api/jobs/{uuid.uuid4()}", {"title": "Changed"}),
        ("delete", f"/api/jobs/{uuid.uuid4()}", None),
    ],
)
def test_jobs_require_authentication(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_cross_user_read_update_delete_search_and_count_isolation(
    jobs_client, job_users
):
    first, second = job_users
    first_job = create_job(
        jobs_client, first, title="Visible Role", company="First Company"
    ).json()
    second_job = create_job(
        jobs_client, second, title="Private Quantum Role", company="Second Company"
    ).json()

    assert jobs_client.get(
        f"/api/jobs/{second_job['id']}", headers=auth_headers(first)
    ).status_code == status.HTTP_404_NOT_FOUND
    assert jobs_client.patch(
        f"/api/jobs/{second_job['id']}",
        json={"title": "Taken"},
        headers=auth_headers(first),
    ).status_code == status.HTTP_404_NOT_FOUND
    assert jobs_client.delete(
        f"/api/jobs/{second_job['id']}", headers=auth_headers(first)
    ).status_code == status.HTTP_404_NOT_FOUND

    first_search = jobs_client.get(
        "/api/jobs?search=quantum", headers=auth_headers(first)
    ).json()
    first_list = jobs_client.get("/api/jobs", headers=auth_headers(first)).json()
    second_search = jobs_client.get(
        "/api/jobs?search=QUANTUM", headers=auth_headers(second)
    ).json()
    assert first_search == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert first_list["total"] == 1
    assert first_list["items"][0]["id"] == first_job["id"]
    assert second_search["total"] == 1
    assert second_search["items"][0]["id"] == second_job["id"]
    assert jobs_client.get(
        f"/api/jobs/{second_job['id']}", headers=auth_headers(second)
    ).status_code == status.HTTP_200_OK


def test_server_managed_fields_cannot_be_created_or_changed(
    jobs_client, job_users, db_session
):
    first, second = job_users
    rejected_create = jobs_client.post(
        "/api/jobs",
        json={
            "title": "Role",
            "company": "Company",
            "owner_id": str(second.id),
            "id": str(uuid.uuid4()),
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        headers=auth_headers(first),
    )
    assert rejected_create.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    job = create_job(jobs_client, first).json()
    rejected_patch = jobs_client.patch(
        f"/api/jobs/{job['id']}",
        json={
            "owner_id": str(second.id),
            "id": str(uuid.uuid4()),
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        headers=auth_headers(first),
    )
    assert rejected_patch.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    stored = db_session.get(SavedJob, uuid.UUID(job["id"]))
    assert stored.owner_id == first.id


def test_different_users_may_save_the_same_source_url(jobs_client, job_users):
    first, second = job_users
    url = "https://jobs.example.com/shared-role"
    first_response = create_job(jobs_client, first, source_url=url)
    second_response = create_job(jobs_client, second, source_url=url)

    assert first_response.status_code == status.HTTP_201_CREATED
    assert second_response.status_code == status.HTTP_201_CREATED
    assert first_response.json()["source_url"] == second_response.json()["source_url"]
    assert first_response.json()["id"] != second_response.json()["id"]


@pytest.mark.parametrize(
    "body",
    [
        {"title": "", "company": "Company"},
        {"title": "   ", "company": "Company"},
        {"title": "Role", "company": "\t"},
        {"title": "x" * 201, "company": "Company"},
        {"title": "Role", "company": "Company", "source_url": "ftp://example.com/job"},
        {"title": "Role", "company": "Company", "source_url": "not-a-url"},
    ],
)
def test_create_validation(jobs_client, job_users, body):
    first, _ = job_users
    response = jobs_client.post("/api/jobs", json=body, headers=auth_headers(first))
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    "patch",
    [
        {"title": None},
        {"company": None},
        {"title": "   "},
        {"company": ""},
        {"is_archived": None},
    ],
)
def test_patch_rejects_invalid_required_values(jobs_client, job_users, patch):
    first, _ = job_users
    job = create_job(jobs_client, first).json()
    response = jobs_client.patch(
        f"/api/jobs/{job['id']}", json=patch, headers=auth_headers(first)
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_patch_can_clear_every_optional_field(jobs_client, job_users):
    first, _ = job_users
    job = create_job(
        jobs_client,
        first,
        location="Remote",
        description="Description",
        source_url="https://example.com/job",
        notes="Notes",
    ).json()

    response = jobs_client.patch(
        f"/api/jobs/{job['id']}",
        json={
            "location": None,
            "description": None,
            "source_url": None,
            "notes": None,
        },
        headers=auth_headers(first),
    )

    assert response.status_code == status.HTTP_200_OK
    for field in ("location", "description", "source_url", "notes"):
        assert response.json()[field] is None
    assert response.json()["title"] == "Backend Engineer"
    assert response.json()["company"] == "Example Systems"


def test_search_matches_title_or_company_case_insensitively(jobs_client, job_users):
    first, _ = job_users
    create_job(jobs_client, first, title="Platform Engineer", company="Acme")
    create_job(jobs_client, first, title="Analyst", company="PLATFORM Labs")
    create_job(jobs_client, first, title="Designer", company="Other")

    response = jobs_client.get(
        "/api/jobs?search=platform", headers=auth_headers(first)
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] == 2
    assert {item["title"] for item in response.json()["items"]} == {
        "Platform Engineer",
        "Analyst",
    }


def test_pagination_is_bounded_and_stable(jobs_client, job_users):
    first, _ = job_users
    for number in range(5):
        assert create_job(
            jobs_client, first, title=f"Role {number}"
        ).status_code == status.HTTP_201_CREATED

    first_page = jobs_client.get(
        "/api/jobs?page=1&page_size=2", headers=auth_headers(first)
    ).json()
    repeated = jobs_client.get(
        "/api/jobs?page=1&page_size=2", headers=auth_headers(first)
    ).json()
    second_page = jobs_client.get(
        "/api/jobs?page=2&page_size=2", headers=auth_headers(first)
    ).json()

    assert first_page == repeated
    assert first_page["total"] == 5
    assert first_page["page"] == 1
    assert first_page["page_size"] == 2
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 2
    assert {item["id"] for item in first_page["items"]}.isdisjoint(
        {item["id"] for item in second_page["items"]}
    )
    assert jobs_client.get(
        "/api/jobs?page=0", headers=auth_headers(first)
    ).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert jobs_client.get(
        "/api/jobs?page_size=101", headers=auth_headers(first)
    ).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_literal_search_wildcards_are_escaped(jobs_client, job_users):
    first, _ = job_users
    create_job(jobs_client, first, title="100% Remote")
    create_job(jobs_client, first, title="Ordinary Role")

    response = jobs_client.get("/api/jobs?search=%25", headers=auth_headers(first))
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total"] == 1


def test_source_url_is_only_stored_and_never_fetched(jobs_client, job_users):
    first, _ = job_users
    response = create_job(
        jobs_client, first, source_url="https://127.0.0.1:1/must-not-be-requested"
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["source_url"] == "https://127.0.0.1:1/must-not-be-requested"
