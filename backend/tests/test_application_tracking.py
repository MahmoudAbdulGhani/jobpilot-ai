import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import (ApplicationPack, ApplicationPackVersion,
                        ApplicationRecord, CandidateProfile, Resume,
                        ResumeExtraction, SavedJob, User)
from app.services.application_tracking_service import create_application

TEST_PASSWORD = "tracking-test-password"


@pytest.fixture()
def tracking_users(db_session):
    first = User(email="tracking-first@jobpilot-test.com",
                 password_hash=hash_password(TEST_PASSWORD))
    second = User(email="tracking-second@jobpilot-test.com",
                  password_hash=hash_password(TEST_PASSWORD))
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)
    return first, second


@pytest.fixture()
def tracking_client(client, db_session):
    def override():
        yield db_session

    client.app.dependency_overrides[get_db] = override
    yield client
    client.app.dependency_overrides.pop(get_db, None)


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def application_payload(job_id, **values):
    return SimpleNamespace(
        job_id=job_id,
        submission_date=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        method="email",
        notes=None,
        status="Applied",
        follow_up_date=None,
        pack_id=None,
        pack_version=None,
        **values,
    )


def test_application_tracking_owner_scoped_record_and_status_history(tracking_client, tracking_users, db_session):
    owner, other = tracking_users
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Example Systems",
                   location="Remote", description="Build APIs", source_url="https://example.com/jobs/1", notes="")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    job_id = job.id

    create = tracking_client.post(
        f"/api/jobs/{job_id}/applications",
        json={
            "submission_date": "2026-09-14T12:00:00Z",
            "method": "email",
            "notes": "Follow up this week.",
            "status": "Applied",
            "follow_up_date": "2026-09-21T12:00:00Z",
        },
        headers=auth_headers(owner),
    )
    assert create.status_code == status.HTTP_201_CREATED, create.text
    created = create.json()
    assert created["job_id"] == str(job_id)
    assert created["method"] == "email"
    assert created["status"] == "Applied"

    duplicate = tracking_client.post(
        f"/api/jobs/{job_id}/applications",
        json={
            "submission_date": "2026-09-14T12:00:00Z",
            "method": "email",
            "notes": "Duplicate.",
            "status": "Applied",
        },
        headers=auth_headers(owner),
    )
    assert duplicate.status_code == status.HTTP_409_CONFLICT, duplicate.text

    update = tracking_client.patch(
        f"/api/jobs/{job_id}/applications/{created['id']}",
        json={"status": "Interview"},
        headers=auth_headers(owner),
    )
    assert update.status_code == status.HTTP_200_OK, update.text
    changed = update.json()
    assert changed["status"] == "Interview"

    repeated = tracking_client.patch(
        f"/api/jobs/{job_id}/applications/{created['id']}",
        json={"status": "Interview"},
        headers=auth_headers(owner),
    )
    assert repeated.status_code == status.HTTP_200_OK, repeated.text

    events = tracking_client.get(
        f"/api/jobs/{job_id}/applications/{created['id']}/events",
        headers=auth_headers(owner),
    )
    assert events.status_code == status.HTTP_200_OK, events.text
    body = events.json()
    assert body["total"] == 2
    assert {item["status"] for item in body["items"]} == {"Applied", "Interview"}


def test_concurrent_duplicate_creation_creates_exactly_one_application(
    test_engine
):
    seed = Session(test_engine)
    owner = User(
        email=f"concurrent-{uuid.uuid4()}@jobpilot-test.com",
        password_hash=hash_password(TEST_PASSWORD),
    )
    seed.add(owner)
    seed.flush()
    job = SavedJob(owner_id=owner.id, title="Concurrent Engineer", company="Example")
    seed.add(job)
    seed.commit()
    seed.refresh(job)
    job_id = job.id
    barrier = __import__("threading").Barrier(2)

    def submit():
        session = Session(test_engine)
        try:
            barrier.wait()
            try:
                create_application(session, owner.id, application_payload(job_id))
                return "created"
            except Exception as error:
                return error
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: submit(), range(2)))
        assert sum(result == "created" for result in results) == 1
        check = Session(test_engine)
        try:
            assert check.scalar(
                select(func.count()).select_from(ApplicationRecord).where(
                    ApplicationRecord.owner_id == owner.id,
                    ApplicationRecord.job_id == job_id,
                )
            ) == 1
        finally:
            check.close()
    finally:
        cleanup = Session(test_engine)
        try:
            cleanup.execute(delete(User).where(User.id == owner.id))
            cleanup.commit()
        finally:
            cleanup.close()


def _pack_fixture(db_session, owner_id, job_id, approved_at=None, number=1):
    profile = db_session.scalar(
        select(CandidateProfile).where(CandidateProfile.owner_id == owner_id)
    )
    if profile is None:
        profile = CandidateProfile(owner_id=owner_id)
        db_session.add(profile)
        db_session.flush()
    resume = Resume(
        owner_id=owner_id, original_filename="cv.pdf", display_name="cv.pdf",
        file_extension="pdf", size_bytes=1,
    )
    db_session.add(resume)
    db_session.flush()
    extraction = ResumeExtraction(
        resume_id=resume.id, status="succeeded", draft_text="captured CV",
        reviewed_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    db_session.add(extraction)
    db_session.flush()
    pack = ApplicationPack(
        owner_id=owner_id, job_id=job_id, profile_id=profile.id,
        resume_id=resume.id, extraction_id=extraction.id,
        idempotency_key=str(uuid.uuid4()), source_hash="source-hash",
        source_snapshot={}, status="ready", current_version=number,
        provider="test", model="test", prompt_version="test",
        deadline=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    db_session.add(pack)
    db_session.flush()
    version = ApplicationPackVersion(
        pack_id=pack.id, number=number,
        cv={"blocks": [{"text": "captured CV"}]},
        cover_letter={"blocks": [{"text": "captured letter"}]},
        approved_at=approved_at,
    )
    db_session.add(version)
    db_session.flush()
    return pack, version


def test_pack_validation_and_application_snapshots_survive_pack_deletion(
    tracking_client, tracking_users, db_session
):
    owner, other = tracking_users
    owner_job = SavedJob(owner_id=owner.id, title="Owner job", company="Example")
    other_job = SavedJob(owner_id=owner.id, title="Other job", company="Example")
    db_session.add_all([owner_job, other_job])
    db_session.flush()
    approved = datetime(2026, 9, 14, tzinfo=timezone.utc)
    valid_pack, valid_version = _pack_fixture(db_session, owner.id, owner_job.id, approved)
    unapproved_pack, _ = _pack_fixture(db_session, owner.id, owner_job.id)
    wrong_job_pack, _ = _pack_fixture(db_session, owner.id, other_job.id, approved)
    wrong_owner_pack, _ = _pack_fixture(db_session, other.id, owner_job.id, approved)
    db_session.commit()

    def create_with(pack):
        return tracking_client.post(
            f"/api/jobs/{owner_job.id}/applications",
            json={
                "submission_date": "2026-09-14T12:00:00Z",
                "method": "email", "status": "Applied",
                "pack_id": str(pack.id), "pack_version": pack.current_version,
            },
            headers=auth_headers(owner),
        )

    assert create_with(unapproved_pack).status_code == status.HTTP_409_CONFLICT
    assert create_with(wrong_owner_pack).status_code == status.HTTP_404_NOT_FOUND
    assert create_with(wrong_job_pack).status_code == status.HTTP_404_NOT_FOUND

    created = create_with(valid_pack)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    application_id = created.json()["id"]
    expected_cv = valid_version.cv
    expected_cover_letter = valid_version.cover_letter
    assert created.json()["cv_snapshot"] == expected_cv
    assert created.json()["cover_letter_snapshot"] == expected_cover_letter

    db_session.execute(
        update(ApplicationPackVersion)
        .where(ApplicationPackVersion.id == valid_version.id)
        .values(cv={"blocks": [{"text": "changed source CV"}]})
    )
    db_session.commit()
    stored = db_session.get(ApplicationRecord, uuid.UUID(application_id))
    assert stored is not None
    assert stored.cv_snapshot == expected_cv
    assert stored.cover_letter_snapshot == expected_cover_letter

    db_session.delete(valid_pack)
    db_session.commit()
    stored = db_session.get(ApplicationRecord, uuid.UUID(application_id))
    assert stored is not None
    assert stored.pack_id is None
    assert stored.cv_snapshot == expected_cv
    assert stored.cover_letter_snapshot == expected_cover_letter


def test_application_tracking_list_route_and_owner_scope(tracking_client, tracking_users, db_session):
    owner, other = tracking_users
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Example Systems",
                   location="Remote", description="Build APIs", source_url="https://example.com/jobs/1", notes="")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    create = tracking_client.post(
        f"/api/jobs/{job.id}/applications",
        json={
            "submission_date": "2026-09-14T12:00:00Z",
            "method": "email",
            "notes": "Follow up this week.",
            "status": "Applied",
            "follow_up_date": "2026-09-21T12:00:00Z",
        },
        headers=auth_headers(owner),
    )
    assert create.status_code == status.HTTP_201_CREATED, create.text
    app_id = create.json()["id"]

    list_all = tracking_client.get(
        "/api/applications?page=1&page_size=10",
        headers=auth_headers(owner),
    )
    assert list_all.status_code == status.HTTP_200_OK, list_all.text
    body = list_all.json()
    assert body["total"] == 1
    assert body["items"][0]["job_id"] == str(job.id)

    other_list = tracking_client.get(
        "/api/applications?page=1&page_size=10",
        headers=auth_headers(other),
    )
    assert other_list.status_code == status.HTTP_200_OK, other_list.text
    assert other_list.json()["total"] == 0

    other_get = tracking_client.get(
        f"/api/jobs/{job.id}/applications/{app_id}",
        headers=auth_headers(other),
    )
    assert other_get.status_code == status.HTTP_404_NOT_FOUND, other_get.text

    other_patch = tracking_client.patch(
        f"/api/jobs/{job.id}/applications/{app_id}",
        json={"status": "Interview"},
        headers=auth_headers(other),
    )
    assert other_patch.status_code == status.HTTP_404_NOT_FOUND, other_patch.text

    other_delete = tracking_client.delete(
        f"/api/jobs/{job.id}/applications/{app_id}",
        headers=auth_headers(other),
    )
    assert other_delete.status_code == status.HTTP_404_NOT_FOUND, other_delete.text
