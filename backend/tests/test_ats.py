"""ATS/readiness reports: explicit checks only, approved packs, owner isolation."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import (ApplicationPack, ApplicationPackVersion, CandidateProfile,
                        Resume, ResumeExtraction, SavedJob, User)
from consent_helpers import grant_consent

TEST_PASSWORD = "ats-test-password"
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
DESCRIPTION = ("We are hiring a Backend Engineer.\n"
               "You must have strong Python and PostgreSQL experience.\n"
               "FastAPI service work is required.")
CV_BLOCKS = [
    {"id": "cv-heading", "kind": "heading", "text": "Curriculum vitae", "evidence": []},
    {"id": "cv-contact", "kind": "paragraph", "text": "Ada Engineer\nada@example.com\n+961 1 234 567",
     "evidence": [{"fact_id": None, "cv_quote": "ada@example.com"}]},
    {"id": "cv-exp", "kind": "paragraph", "text": "Backend Engineer at Acme 2021 - 2024. Built Python and PostgreSQL FastAPI services.",
     "evidence": [{"fact_id": "fact-1", "cv_quote": "Built Python and PostgreSQL FastAPI services."}]},
]
LETTER_BLOCKS = [
    {"id": "letter-heading", "kind": "heading", "text": "Cover letter", "evidence": []},
    {"id": "letter-1", "kind": "paragraph", "text": "My background includes Python and PostgreSQL service work.",
     "evidence": [{"fact_id": "fact-1", "cv_quote": None}]},
]


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


def approved_pack(db_session, owner, job, approved=True):
    from sqlalchemy import select
    profile = db_session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner.id))
    if profile is None:
        profile = CandidateProfile(owner_id=owner.id, headline="Backend engineer",
                                   skills=["Python", "PostgreSQL", "Python"],
                                   experience=[{"title": "Backend Engineer", "organization": "Acme"}])
        db_session.add(profile)
        db_session.flush()
    resume = Resume(owner_id=owner.id, original_filename="cv.pdf", display_name="cv.pdf",
                    file_extension="pdf", size_bytes=1)
    db_session.add(resume)
    db_session.flush()
    extraction = ResumeExtraction(resume_id=resume.id, status="succeeded",
                                  draft_text="captured CV", reviewed_at=NOW)
    db_session.add(extraction)
    db_session.flush()
    pack = ApplicationPack(owner_id=owner.id, job_id=job.id, profile_id=profile.id,
                           resume_id=resume.id, extraction_id=extraction.id,
                           idempotency_key=str(uuid.uuid4()), source_hash="hash",
                           source_snapshot={}, status="ready", current_version=1,
                           provider="test", model="test", prompt_version="test",
                           deadline=NOW)
    db_session.add(pack)
    db_session.flush()
    version = ApplicationPackVersion(pack_id=pack.id, number=1,
                                     cv={"blocks": CV_BLOCKS},
                                     cover_letter={"blocks": LETTER_BLOCKS},
                                     approved_at=NOW if approved else None)
    db_session.add(version)
    db_session.commit()
    return pack


def test_ats_report_checks_and_readiness(client, db_session):
    owner = make_user(db_session, "ats-first@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   location="Remote", description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    pack = approved_pack(db_session, owner, job)
    caller = api_client(client, db_session)
    try:
        created = caller.post(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports",
                              json={}, headers=auth(owner))
        assert created.status_code == status.HTTP_201_CREATED, created.text
        body = created.json()
        assert body["report_version"] == "ats-v1"
        assert body["pack_version"] == 1
        checks = {check["id"]: check for check in body["checks"]}
        assert set(checks) == {"keyword_coverage", "contact_fields", "date_consistency",
                               "duplicate_skills", "unsupported_claims", "evidence_gaps"}
        assert all(check["status"] in {"pass", "warn", "fail"} for check in body["checks"])
        assert all(check["evidence"] for check in body["checks"])
        assert checks["contact_fields"]["status"] == "pass"
        assert checks["date_consistency"]["status"] == "pass"
        assert checks["unsupported_claims"]["status"] == "pass"
        # Profile lists Python twice: the duplicate-skills check must flag it.
        assert checks["duplicate_skills"]["status"] == "warn"
        assert isinstance(body["readiness_score"], int)
        assert 0 <= body["readiness_score"] <= 100
        expected = round(100 * sum(
            {"pass": 1.0, "warn": 0.5, "fail": 0.0}[c["status"]] for c in body["checks"]) / len(body["checks"]))
        assert body["readiness_score"] == expected, "readiness derives only from explicit checks"

        latest = caller.get(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports/latest",
                            headers=auth(owner))
        assert latest.status_code == status.HTTP_200_OK, latest.text
        assert latest.json()["id"] == body["id"]

        history = caller.get(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports?page=1&page_size=10",
                             headers=auth(owner))
        assert history.json()["total"] == 1

        removed = caller.delete(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports/{body['id']}",
                                headers=auth(owner))
        assert removed.status_code == status.HTTP_204_NO_CONTENT
    finally:
        client.app.dependency_overrides.pop(get_db, None)


def start(client, db_session, user):
    def override_db():
        yield db_session
    client.app.dependency_overrides[get_db] = override_db
    return client


def seed_source(db_session, owner, job):
    """Profile + confirmed resume extraction so pack generation can capture them."""
    profile = db_session.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner.id))
    if profile is None:
        profile = CandidateProfile(owner_id=owner.id, headline="Backend engineer",
                                   skills=["Python", "PostgreSQL", "Python"],
                                   experience=[{"title": "Backend Engineer", "organization": "Acme"}])
        db_session.add(profile)
        db_session.flush()
    resume = Resume(owner_id=owner.id, original_filename="cv.pdf", display_name="cv.pdf",
                    file_extension="pdf", size_bytes=1)
    db_session.add(resume)
    db_session.flush()
    extraction = ResumeExtraction(resume_id=resume.id, status="succeeded",
                                  draft_text="Backend Engineer at Acme\nBuilt Python and PostgreSQL services.",
                                  reviewed_at=NOW)
    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def test_pack_generation_repairs_unsupported_wording_without_another_provider_call(
        client, db_session, monkeypatch):
    from app.services import application_pack_service
    from app.services.ai_provider import DeterministicTestProvider

    owner = make_user(db_session, "pack-repair-owner@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   location="Remote", description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    resume = seed_source(db_session, owner, job)
    grant_consent(db_session, owner.id, "ai_application_packs")
    settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    calls = []

    class MockProvider:
        name = "mock"
        model = "mock-pack"

        def create_pack(self, source):
            calls.append(source)
            output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
            output["cv"]["blocks"][1]["text"] = "Accomplished professional at Acme"
            output["cv"]["blocks"][1]["evidence"][0]["cv_quote"] = "Backend  Engineer at Acme"
            return output

    monkeypatch.setattr(application_pack_service, "pack_provider_for", lambda _: MockProvider())
    caller = start(client, db_session, owner)
    try:
        client.app.dependency_overrides[get_settings] = lambda: settings
        response = caller.post(f"/api/jobs/{job.id}/application-packs",
                               json={"resume_id": str(resume.id), "idempotency_key": "pack-repair-001"},
                               headers=auth(owner))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ready"
        assert len(calls) == 1
        assert body["version"]["cv"]["blocks"][1]["text"] == "Backend Engineer at Acme"
        assert "exact cited source text" in " ".join(body["review_notes"])
        assert "matched to exact passages" in " ".join(body["review_notes"])
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("revoke_at_dispatch", [False, True])
def test_ats_improve_closed_loop(client, db_session, monkeypatch, revoke_at_dispatch):
    owner = make_user(db_session, "ats-improve-owner@jobpilot-test.com")
    other = make_user(db_session, "ats-improve-foreign@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   location="Remote", description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    resume = seed_source(db_session, owner, job)

    test_settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True,
        "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = start(client, db_session, owner)
    grant_consent(db_session, owner.id, "ai_application_packs")
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        opened = caller.post(f"/api/jobs/{job.id}/application-packs",
                             json={"resume_id": str(resume.id), "idempotency_key": "pack-00000001"},
                             headers=auth(owner))
        assert opened.status_code == status.HTTP_200_OK, opened.text
        pack_body = opened.json()
        pack_id = pack_body["id"]
        assert pack_body["current_version"] == 1

        approved = caller.post(f"/api/jobs/{job.id}/application-packs/{pack_id}/approve",
                               json={"expected_version": 1, "idempotency_key": "approve-000001"},
                               headers=auth(owner))
        assert approved.status_code == status.HTTP_200_OK, approved.text
        assert approved.json()["version"]["number"] == 1

        report = caller.post(f"/api/jobs/{job.id}/packs/{pack_id}/ats-reports",
                             json={}, headers=auth(owner))
        assert report.status_code == status.HTTP_201_CREATED, report.text
        report_id = report.json()["id"]

        if revoke_at_dispatch:
            from app.services import application_pack_service, ai_usage
            from unittest.mock import Mock
            original = ai_usage.reserve
            def revoke(*args, **kwargs):
                token = original(*args, **kwargs)
                grant_consent(db_session, owner.id, "ai_application_packs", allowed=False)
                return token
            provider = Mock()
            monkeypatch.setattr(application_pack_service, "pack_provider_for", lambda _: provider)
            monkeypatch.setattr(ai_usage, "reserve", revoke)
        improved = caller.post(f"/api/jobs/{job.id}/packs/{pack_id}/ats-reports/{report_id}/improve",
                               json={"idempotency_key": "improve-0001"}, headers=auth(owner))
        if revoke_at_dispatch:
            assert improved.status_code == 403, improved.text
            provider.improve_pack.assert_not_called()
            versions = caller.get(f"/api/jobs/{job.id}/application-packs/{pack_id}/versions", headers=auth(owner)).json()["items"]
            assert len(versions) == 1 and versions[0]["approved_at"]
            return
        assert improved.status_code == status.HTTP_201_CREATED, improved.text
        body = improved.json()
        assert body["report_id"] == report_id
        assert body["pack_id"] == pack_id
        assert body["approved_version"] == 1
        assert body["version_number"] == 2, "improvement appends a new draft version"
        assert isinstance(body["preview_readiness"], int)
        assert 0 <= body["preview_readiness"] <= 100
        assert {check["id"] for check in body["preview_checks"]} == {
            "keyword_coverage", "contact_fields", "date_consistency",
            "duplicate_skills", "unsupported_claims", "evidence_gaps"}
        assert body["review_notes"]

        versions = caller.get(f"/api/jobs/{job.id}/application-packs/{pack_id}/versions?page=1&page_size=20",
                              headers=auth(owner)).json()["items"]
        by_number = {item["number"]: item for item in versions}
        assert set(by_number) == {1, 2}
        assert by_number[1]["approved_at"], "the original approved version stays immutable"
        assert by_number[2]["approved_at"] is None, "the improved draft is never auto-approved"

        replay = caller.post(f"/api/jobs/{job.id}/packs/{pack_id}/ats-reports/{report_id}/improve",
                             json={"idempotency_key": "improve-0001"}, headers=auth(owner))
        assert replay.status_code == status.HTTP_201_CREATED, replay.text
        assert replay.json()["version_number"] == 2, "replay returns the same version"
        again = caller.get(f"/api/jobs/{job.id}/application-packs/{pack_id}/versions?page=1&page_size=20",
                           headers=auth(owner)).json()["items"]
        assert len(again) == 2, "replay must not create a duplicate draft"

        approved2 = caller.post(f"/api/jobs/{job.id}/application-packs/{pack_id}/approve",
                                json={"expected_version": 2, "idempotency_key": "approve-000002"},
                                headers=auth(owner))
        assert approved2.status_code == status.HTTP_200_OK, approved2.text
        assert approved2.json()["version"]["number"] == 2

        rerun = caller.post(f"/api/jobs/{job.id}/packs/{pack_id}/ats-reports",
                            json={"pack_version": 2}, headers=auth(owner))
        assert rerun.status_code == status.HTTP_201_CREATED, rerun.text
        assert rerun.json()["pack_version"] == 2, "checks re-run on the approved improved draft"

        foreign = caller.post(f"/api/jobs/{job.id}/packs/{pack_id}/ats-reports/{rerun.json()['id']}/improve",
                              json={"idempotency_key": "improve-0003"}, headers=auth(other))
        assert foreign.status_code == status.HTTP_404_NOT_FOUND, foreign.text
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_ats_improve_guards(client, db_session):
    owner = make_user(db_session, "ats-guard-owner@jobpilot-test.com")
    other = make_user(db_session, "ats-guard-foreign@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    pack = approved_pack(db_session, owner, job, approved=True)
    test_settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True,
        "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True,
        "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = start(client, db_session, owner)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        missing = caller.post(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports",
                              json={}, headers=auth(owner)).json()
        foreign = caller.post(
            f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports/{missing['id']}/improve",
            json={"idempotency_key": "improve-9001"}, headers=auth(other))
        assert foreign.status_code == status.HTTP_404_NOT_FOUND, foreign.text

        missing_report = caller.post(
            f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports/{uuid.uuid4()}/improve",
            json={"idempotency_key": "improve-9002"}, headers=auth(owner))
        assert missing_report.status_code == status.HTTP_404_NOT_FOUND, missing_report.text

        invalid = caller.post(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports/{missing['id']}/improve",
                              json={"idempotency_key": "short"}, headers=auth(owner))
        assert invalid.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, invalid.text
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_ats_report_guards(client, db_session):
    owner = make_user(db_session, "ats-second@jobpilot-test.com")
    other = make_user(db_session, "ats-third@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    pack = approved_pack(db_session, owner, job)
    draft = approved_pack(db_session, owner, job, approved=False)
    caller = api_client(client, db_session)
    try:
        unapproved = caller.post(f"/api/jobs/{job.id}/packs/{draft.id}/ats-reports",
                                 json={}, headers=auth(owner))
        assert unapproved.status_code == status.HTTP_409_CONFLICT, unapproved.text
        foreign = caller.post(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports",
                              json={}, headers=auth(other))
        assert foreign.status_code == status.HTTP_404_NOT_FOUND, foreign.text
        missing = caller.post(f"/api/jobs/{job.id}/packs/{pack.id}/ats-reports",
                              json={"pack_version": 99}, headers=auth(owner))
        assert missing.status_code == status.HTTP_404_NOT_FOUND, missing.text
    finally:
        client.app.dependency_overrides.pop(get_db, None)


def test_generated_pack_without_consent_never_calls_provider(client, db_session, monkeypatch):
    from app.services import application_pack_service
    owner = make_user(db_session, "ats-no-consent@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    resume = seed_source(db_session, owner, job)
    test_settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    def forbidden(*a): pytest.fail("Pack provider must not be called without consent")
    monkeypatch.setattr(application_pack_service, "pack_provider_for", forbidden)
    caller = start(client, db_session, owner)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        response = caller.post(f"/api/jobs/{job.id}/application-packs",
                               json={"resume_id": str(resume.id), "idempotency_key": "pack-no-consent"},
                               headers=auth(owner))
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
        assert "consent" in response.json()["detail"].casefold()
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_pack_consent_revoked_after_reservation_finalizes_idempotently(client, db_session, monkeypatch):
    from unittest.mock import Mock
    from sqlalchemy import select
    from app.models import AIUsage, ApplicationPack, UsageReservation
    from app.services import application_pack_service, ai_usage

    owner = make_user(db_session, "pack-consent-race@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    resume = seed_source(db_session, owner, job)
    grant_consent(db_session, owner.id, "ai_application_packs")
    test_settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = start(client, db_session, owner)
    original_reserve = ai_usage.reserve
    original_provider_for = application_pack_service.pack_provider_for
    provider = Mock()
    provider.name, provider.model = "must-not-run", "must-not-run"

    def revoke_after_reservation(*args, **kwargs):
        token = original_reserve(*args, **kwargs)
        grant_consent(db_session, owner.id, "ai_application_packs", allowed=False)
        return token

    monkeypatch.setattr(ai_usage, "reserve", revoke_after_reservation)
    monkeypatch.setattr(application_pack_service, "pack_provider_for", lambda _: provider)
    payload = {"resume_id": str(resume.id), "idempotency_key": "pack-consent-race"}
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        denied = caller.post(f"/api/jobs/{job.id}/application-packs",
                             json=payload, headers=auth(owner))
        assert denied.status_code == 403
        provider.create_pack.assert_not_called()

        pack = db_session.scalar(select(ApplicationPack).where(
            ApplicationPack.idempotency_key == payload["idempotency_key"]))
        assert pack.status == "failed" and "cancelled" in pack.outcome_message
        usage = db_session.get(AIUsage, owner.id)
        assert usage.active_token is None and usage.active_until is None
        released = db_session.scalar(select(UsageReservation).where(
            UsageReservation.owner_id == owner.id))
        assert released.released_at is not None

        grant_consent(db_session, owner.id, "ai_application_packs")
        same = caller.post(f"/api/jobs/{job.id}/application-packs",
                           json=payload, headers=auth(owner))
        assert same.status_code == 200 and same.json()["id"] == str(pack.id)
        provider.create_pack.assert_not_called()

        monkeypatch.setattr(ai_usage, "reserve", original_reserve)
        monkeypatch.setattr(application_pack_service, "pack_provider_for", original_provider_for)
        fresh = caller.post(f"/api/jobs/{job.id}/application-packs",
                            json={**payload, "idempotency_key": "pack-consent-race-retry"},
                            headers=auth(owner))
        assert fresh.status_code == 200 and fresh.json()["status"] == "ready"
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)


def test_unsupported_draft_is_never_ready_and_approval_still_409(client, db_session, monkeypatch):
    from app.services.ai_provider import DeterministicTestProvider
    from app.schemas.application_packs import PackProviderOutput
    from app.services import application_pack_service
    owner = make_user(db_session, "ats-unsupported@jobpilot-test.com")
    job = SavedJob(owner_id=owner.id, title="Backend Engineer", company="Cedar Labs",
                   description=DESCRIPTION)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    resume = seed_source(db_session, owner, job)
    grant_consent(db_session, owner.id, "ai_application_packs")

    class Unsupported(DeterministicTestProvider):
        def create_pack(self, source):
            output = super().create_pack(source).model_dump(mode="json")
            output["cover_letter"]["blocks"][1].update(
                text="I built the booking API using Python and PostgreSQL.",
                evidence=[{"fact_id": f"fact-{n}", "cv_quote": None} for n in (2, 3, 4)])
            return PackProviderOutput.model_validate(output)

    monkeypatch.setattr(application_pack_service, "pack_provider_for", lambda settings: Unsupported())
    test_settings = get_settings().model_copy(update={
        "JOBPILOT_AI_ENABLED": True, "JOBPILOT_AI_TEST_PROVIDER": True,
        "E2E_TEST_MODE": True, "POSTGRES_DB": get_settings().POSTGRES_TEST_DB,
    })
    caller = start(client, db_session, owner)
    try:
        client.app.dependency_overrides[get_settings] = lambda: test_settings
        opened = caller.post(f"/api/jobs/{job.id}/application-packs",
                             json={"resume_id": str(resume.id), "idempotency_key": "pack-unsupported"},
                             headers=auth(owner))
        assert opened.status_code == status.HTTP_200_OK, opened.text
        body = opened.json()
        assert body["status"] == "failed"
        assert body["current_version"] == 0
        assert "not supported" in body["outcome_message"]
        ids = caller.get(f"/api/jobs/{job.id}/application-packs", headers=auth(owner)).json()["items"]
        pack_id = next(item["id"] for item in ids if item["status"] == "failed")
        blocked = caller.post(f"/api/jobs/{job.id}/application-packs/{pack_id}/approve",
                              json={"expected_version": 1, "idempotency_key": "approve-unsupported"},
                              headers=auth(owner))
        assert blocked.status_code == status.HTTP_409_CONFLICT, blocked.text
    finally:
        client.app.dependency_overrides.pop(get_settings, None)
        client.app.dependency_overrides.pop(get_db, None)
