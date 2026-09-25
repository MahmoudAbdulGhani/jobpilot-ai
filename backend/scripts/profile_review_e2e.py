"""Seed/read synthetic browser fixtures through independent PostgreSQL connections.

No production target, schema changes, AI calls, or unscoped cleanup are allowed.
The browser harness owns account creation and removal.
"""
import json
import sys
from pathlib import Path
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import User, CandidateProfile, ResumeExtraction, Resume, ProfileSuggestionSet, ProfileGenerationRequest, UsageReservation
from app.schemas.profile_suggestions import ProviderSuggestionOutput
from app.services.profile_suggestion_service import source_hash, validate_output, profile_revision


def main():
    settings = get_settings()
    if settings.POSTGRES_HOST not in {"127.0.0.1", "localhost"} or settings.POSTGRES_TEST_DB != "jobpilot_test":
        raise RuntimeError("Only the local jobpilot_test database is allowed.")
    data = json.load(sys.stdin)
    if not data["email"].startswith("e2e-profile-review-") or not data["email"].endswith("@jobpilot-test.com"):
        raise RuntimeError("Only this test's synthetic accounts are allowed.")
    engine = create_engine(settings.test_database_url, hide_parameters=True)
    try:
        with Session(engine) as db:
            owner = db.scalar(select(User).where(User.email == data["email"]))
            assert owner is not None
            if data["action"] == "seed":
                resume = db.scalar(select(Resume).where(Resume.id == uuid.UUID(data["resume_id"]), Resume.owner_id == owner.id))
                assert resume is not None
                extraction = db.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume.id))
                assert extraction is not None and extraction.reviewed_at is not None
                output = ProviderSuggestionOutput.model_validate(data["output"])
                accepted, partial = validate_output(output, extraction.draft_text)
                assert not partial and len(accepted) == len(output.suggestions)
                profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner.id))
                assert profile is None
                record = ProfileSuggestionSet(owner_id=owner.id, resume_id=resume.id, extraction_id=extraction.id,
                    source_text=extraction.draft_text, source_hash=source_hash(extraction.draft_text), source_reviewed_at=extraction.reviewed_at,
                    profile_revision=profile_revision(profile), status=data.get("status", "ready"), suggestions=accepted + [
                        {"id": f"not-found:{field}", "field": field, "status": "not_found", "value": None, "evidence": []}
                        for field in output.not_found], provider="deterministic-test", model="synthetic-browser-fixture", prompt_version=data.get("prompt_version", "test"))
                if data.get("status") == "applied":
                    saved = CandidateProfile(owner_id=owner.id)
                    db.add(saved)
                    db.flush()
                    record.applied_at = datetime.now(timezone.utc)
                    record.apply_result = {"applied": accepted, "manual_fields": {}, "profile_id": str(saved.id)}
                    record.applied_selection_hash = "synthetic-applied-history"
                db.add(record)
                db.commit()
                print(json.dumps({"id": str(record.id)}))
            elif data["action"] == "check":
                profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner.id))
                assert profile is not None
                for field, expected in data["expected"].items():
                    assert getattr(profile, field) == expected, f"Stored {field} does not match"
                record = db.scalar(select(ProfileSuggestionSet).where(ProfileSuggestionSet.id == uuid.UUID(data["set_id"]), ProfileSuggestionSet.owner_id == owner.id))
                assert record.status == data["status"]
                assert bool(record.applied_at) == (data["status"] == "applied")
                print(json.dumps({"matched": True, "fields": len(data["expected"])}))
            elif data["action"] == "quota":
                requests = list(db.scalars(select(ProfileGenerationRequest).where(
                    ProfileGenerationRequest.owner_id == owner.id,
                ).order_by(ProfileGenerationRequest.created_at, ProfileGenerationRequest.id)))
                reservations = list(db.scalars(select(UsageReservation).where(
                    UsageReservation.owner_id == owner.id,
                    UsageReservation.feature == "profile",
                )))
                print(json.dumps({"kinds": [item.kind for item in requests],
                                  "reservation_count": len(reservations)}))
            else:
                raise ValueError("Unknown action")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
