"""All dispatch entry points must fail closed before reaching a provider."""
import uuid
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models import User
from app.services import (application_pack_service, interview_service, interview_voice,
                          job_fit_service, privacy_service, profile_suggestion_service, qa_service)
from consent_helpers import grant_consent


@pytest.mark.parametrize("state", ["missing", "denied", "revoked", "other-owner"])
@pytest.mark.parametrize("feature", ["profile", "fit", "pack", "ats", "interview", "voice", "qa"])
def test_every_ai_entry_point_denies_without_owner_consent(db_session, monkeypatch, state, feature):
    owner = User(email=f"consent-{uuid.uuid4()}@example.test", password_hash="unused")
    other = User(email=f"consent-{uuid.uuid4()}@example.test", password_hash="unused")
    db_session.add_all([owner, other]); db_session.commit()
    key = {"profile": "ai_profile_suggestions", "fit": "ai_job_fit", "pack": "ai_application_packs",
           "ats": "ai_application_packs", "interview": "ai_interview", "voice": "ai_voice", "qa": "ai_qa"}[feature]
    if state == "other-owner":
        grant_consent(db_session, other.id, key)
    elif state != "missing":
        if state == "revoked":
            grant_consent(db_session, owner.id, key)
            assert privacy_service.is_consented(db_session, owner.id, key)
        grant_consent(db_session, owner.id, key, allowed=False)
    provider = Mock(side_effect=AssertionError("Provider must never be constructed"))
    for module, factory in [(profile_suggestion_service, "provider_for"), (job_fit_service, "provider_for"),
                            (application_pack_service, "pack_provider_for"), (interview_service, "provider_for"),
                            (interview_voice, "provider_for"), (qa_service, "_provider_for")]:
        monkeypatch.setattr(module, factory, provider)
    settings = get_settings().model_copy(update={"JOBPILOT_AI_ENABLED": True})
    dispatch = {
        "profile": lambda: profile_suggestion_service.generate(db_session, owner_id=owner.id, resume=None, settings=settings),
        "fit": lambda: job_fit_service.generate(db_session, owner_id=owner.id, job=None, key="denied", settings=settings),
        "pack": lambda: application_pack_service.generate(db_session, owner.id, uuid.uuid4(), None, settings),
        "ats": lambda: application_pack_service.improve_pack(db_session, owner.id, uuid.uuid4(), uuid.uuid4(),
                    report_id=uuid.uuid4(), target_version=1, checks=[], readiness_score=0, body=None, settings=settings),
        "interview": lambda: interview_service.advance(db_session, owner.id, uuid.uuid4(), None, settings),
        "voice": lambda: interview_voice.run(db_session, owner.id, uuid.uuid4(), uuid.uuid4(), 1, True, "tts", settings),
        "qa": lambda: qa_service.answer(db_session, owner.id, "jobs", "Python", 10, settings),
    }
    with pytest.raises(HTTPException) as error:
        dispatch[feature]()
    assert error.value.status_code == 403
    assert "consent" in error.value.detail.lower()
    provider.assert_not_called()
