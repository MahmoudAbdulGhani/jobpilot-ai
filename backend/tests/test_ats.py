"""ATS/readiness reports: explicit checks only, approved packs, owner isolation."""
import uuid
from datetime import datetime, timezone

from fastapi import status

from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.models import (ApplicationPack, ApplicationPackVersion, CandidateProfile,
                        Resume, ResumeExtraction, SavedJob, User)

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
