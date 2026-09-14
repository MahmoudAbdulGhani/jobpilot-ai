import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidateProfile
from app.schemas.profile import CandidateProfileUpdate


def get_candidate_profile(
    session: Session, *, owner_id: uuid.UUID
) -> CandidateProfile | None:
    return session.scalar(
        select(CandidateProfile).where(CandidateProfile.owner_id == owner_id)
    )


def upsert_candidate_profile(
    session: Session, *, owner_id: uuid.UUID, data: CandidateProfileUpdate
) -> CandidateProfile:
    profile = get_candidate_profile(session, owner_id=owner_id)
    if profile is None:
        values = data.model_dump(mode="json")
        profile = CandidateProfile(
            owner_id=owner_id,
            **values,
            ai_provenance={field: {"origin": "user"} for field in values},
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile
    values = data.model_dump(exclude_unset=True, mode="json")
    provenance = dict(profile.ai_provenance or {})
    for field, value in values.items():
        setattr(profile, field, value)
        provenance[field] = {"origin": "user"}
    profile.ai_provenance = provenance
    session.commit()
    session.refresh(profile)
    return profile
