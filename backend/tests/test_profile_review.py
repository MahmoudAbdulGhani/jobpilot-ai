"""Review is read-only; confirmed saves persist the complete accepted form."""
import uuid

import pytest
from sqlalchemy import select

from app.models import CandidateProfile, ProfileSuggestionSet
from app.schemas.profile_suggestions import ProviderSuggestionOutput
from app.services import profile_suggestion_service
from consent_helpers import grant_consent
from tests.test_profile_suggestions import (
    suggestion_client, suggestion_users, confirmed_resume, headers, enable_fake,
)


@pytest.fixture()
def ready(suggestion_client, suggestion_users, db_session, monkeypatch):
    owner, other = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    source = "Tripoli Python SQL Cedar University BSc Computer Science 2022 Academy AWS 2026 Arabic Native English Professional"
    resume = confirmed_resume(suggestion_client, owner, source)
    values = [
        ("location", "Tripoli"), ("skills", ["Python", "SQL"]),
        ("education", {"school": "Cedar University", "degree": "BSc", "field": "Computer Science", "period": "2022"}),
        ("education", {"school": "Academy", "degree": "AWS", "field": None, "period": "2026"}),
        ("languages", {"name": "Arabic", "proficiency": "native"}),
        ("languages", {"name": "English", "proficiency": "professional"}),
    ]
    class Provider:
        name = "deterministic-test"
        model = "synthetic-v1"
        def suggest(self, _source):
            return ProviderSuggestionOutput.model_validate({"suggestions": [
                {"id": f"s-{i}", "field": field, "value": value, "evidence": [{"quote": source}]}
                for i, (field, value) in enumerate(values)
            ], "not_found": ["target_roles", "remote_preference", "work_authorization", "salary_preference"]})
    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Provider())
    response = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume}", headers=headers(owner))
    assert response.status_code == 200
    body = response.json()
    selections = [item for item in body["suggestions"] if item.get("status") != "not_found"]
    # A review/save must not dispatch generation, including with a stale profile.
    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: pytest.fail("Unexpected AI call"))
    return owner, other, body, selections


def stored(db, owner):
    db.expire_all()
    return db.connection().execute(select(CandidateProfile.__table__).where(
        CandidateProfile.owner_id == owner.id)).mappings().one_or_none()


@pytest.mark.parametrize("initial_role", [False, True])
def test_focus_recovers_two_roles_and_saves_manual_addition(suggestion_client, suggestion_users, db_session, monkeypatch, initial_role):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    source = ("PROFESSIONAL EXPERIENCE\n"
              "Developer - Cedar Labs June 2022 - July 2024\nBuilt APIs\nImproved reporting queries\n"
              "Engineer - Pine Works Jan 2020 - May 2022\nBuilt tests\n"
              "PROJECT EXPERIENCE\nDeveloper - Demo App 2025\nBuilt a prototype")
    resume = confirmed_resume(suggestion_client, owner, source)
    calls = []

    class Provider:
        name = "deterministic-test"
        model = "synthetic-v1"

        def suggest(self, text):
            calls.append(text)
            if initial_role:
                return ProviderSuggestionOutput.model_validate({"suggestions": [
                    {"id": "initial-role", "field": "experience",
                     "value": {"title": "Developer", "organization": "Cedar Labs",
                               "period": "June 2022 - July 2024", "notes": "Built APIs"},
                     "evidence": [{"quote": "Developer - Cedar Labs June 2022 - July 2024"},
                                  {"quote": "Built APIs"}]},
                ]})
            return ProviderSuggestionOutput(suggestions=[], not_found=["experience"])

        def suggest_experience(self, text):
            calls.append(text)
            return ProviderSuggestionOutput.model_validate({"suggestions": [
                {"id": "role-1", "field": "experience",
                 "value": {"title": "Developer", "organization": "Cedar Labs", "period": "June 2022 - July 2024", "notes": "Built APIs"},
                 "evidence": [{"quote": "Developer - Cedar Labs June 2022 - July 2024"}, {"quote": "Built APIs"}]},
                {"id": "role-2", "field": "experience",
                 "value": {"title": "Engineer", "organization": "Pine Works", "period": "Jan 2020 - May 2022", "notes": "Built tests"},
                 "evidence": [{"quote": "Engineer - Pine Works Jan 2020 - May 2022"}, {"quote": "Built tests"}]},
            ]})

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Provider())
    auth = headers(owner)
    record = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume}", headers=auth).json()
    assert len(calls) == 2 and "PROJECT EXPERIENCE" not in calls[1]
    selected = [item for item in record["suggestions"] if item["field"] == "experience" and item.get("status") != "not_found"]
    assert len(selected) == 2 and record["field_statuses"]["experience"] == "suggested"
    assert selected[0]["value"]["notes"] == "Built APIs\nImproved reporting queries"
    added = {"title": "Mentor", "organization": "Community Lab", "period": None, "notes": None}
    payload = {"selections": selected, "manual_experience_entries": [added]}
    url = f"/api/profile-suggestions/{record['id']}"
    review = suggestion_client.post(url + "/review", headers=auth, json=payload)
    assert review.status_code == 200
    assert stored(db_session, owner) is None
    assert len(review.json()["proposed_profile"]["experience"]) == 3
    payload["reviewed_profile_revision"] = review.json()["reviewed_profile_revision"]
    saved = suggestion_client.post(url + "/apply", headers=auth, json=payload)
    assert saved.status_code == 200
    assert len(stored(db_session, owner)["experience"]) == 3
    assert stored(db_session, owner)["experience"][0]["notes"] == "Built APIs\nImproved reporting queries"
    assert [entry["origin"] for entry in stored(db_session, owner)["ai_provenance"]["experience"]] == ["ai", "ai", "user"]
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 200


def test_visible_unvalidated_work_history_needs_review(suggestion_client, suggestion_users, db_session, monkeypatch):
    owner, _ = suggestion_users
    grant_consent(db_session, owner.id, "ai_profile_suggestions")
    enable_fake(monkeypatch)
    resume = confirmed_resume(suggestion_client, owner,
                              "PROFESSIONAL EXPERIENCE\nDeveloper - Cedar Labs June 2022 - July 2024\nBuilt APIs\nPROJECT EXPERIENCE\nDemo 2025")

    class Provider:
        name = "deterministic-test"
        model = "synthetic-v1"

        def suggest(self, _):
            return ProviderSuggestionOutput(suggestions=[], not_found=["experience"])

        def suggest_experience(self, _):
            return ProviderSuggestionOutput(suggestions=[], not_found=["experience"])

    monkeypatch.setattr(profile_suggestion_service, "provider_for", lambda settings: Provider())
    record = suggestion_client.post(f"/api/profile-suggestions/resumes/{resume}", headers=headers(owner)).json()
    assert record["field_statuses"]["experience"] == "needs_review"
    assert not any(item["field"] == "experience" for item in record["suggestions"])


def test_experience_evidence_cannot_combine_roles():
    from app.services.evidence_validation import supported_experience
    source = ("PROFESSIONAL EXPERIENCE\nDeveloper - Cedar Labs June 2022 - July 2024\nBuilt APIs\n"
              "Engineer - Pine Works Jan 2020 - May 2022\nBuilt tests\nPROJECT EXPERIENCE\nDemo 2025")
    value = {"title": "Developer", "organization": "Pine Works", "period": None, "notes": "Built APIs"}
    assert not supported_experience(value, ["Developer - Cedar Labs June 2022 - July 2024", "Engineer - Pine Works Jan 2020 - May 2022", "Built APIs"], source)


def test_generation_keeps_role_header_when_duty_note_is_unsupported():
    source = "PROFESSIONAL EXPERIENCE\nDeveloper - Cedar Labs June 2022 - July 2024\nBuilt APIs\nPROJECT EXPERIENCE\nDemo 2025"
    output = ProviderSuggestionOutput.model_validate({"suggestions": [{
        "id": "experience-1", "field": "experience",
        "value": {"title": "Developer", "organization": "Cedar Labs", "period": "June 2022 - July 2024", "notes": "Managed a global team"},
        "evidence": [{"quote": "Developer - Cedar Labs June 2022 - July 2024"}, {"quote": "Built APIs"}],
    }]})
    assert profile_suggestion_service.validate_output(output, source)[0] == []
    accepted, partial = profile_suggestion_service.validate_output(output, source, salvage_experience=True)
    assert partial and len(accepted) == 1
    assert accepted[0]["value"]["notes"] == "Built APIs"
    assert accepted[0]["evidence"] == [{"quote": "Developer - Cedar Labs June 2022 - July 2024\nBuilt APIs"}]


def test_generation_restores_every_role_duty_without_copying_projects():
    source = (
        "PROFESSIONAL EXPERIENCE\n"
        "Backend Developer - Cedar Labs Dec 2025 - Jan 2026\n"
        "• Developed PHP MVC modules with search, filtering, and pagination.\n"
        "• Wrote MySQL queries for order and profit reporting.\n"
        "• Built administration interfaces with AJAX and\n"
        "  added reusable validation for incoming data.\n"
        "\n"
        "• Reduced repeat database queries by caching reports.\n"
        "• Prepared 2025 reporting exports for finance.\n"
        "Engineer - Pine Works Jan 2024 - Nov 2025\n"
        "• Maintained internal Python services.\n"
        "PROJECT EXPERIENCE\n"
        "• Built a personal demo application."
    )
    output = ProviderSuggestionOutput.model_validate({"suggestions": [
        {"id": "role-1", "field": "experience",
         "value": {"title": "Backend Developer", "organization": "Cedar Labs",
                   "period": "Dec 2025 - Jan 2026", "notes": "Developed PHP MVC modules"},
         "evidence": [{"quote": "Backend Developer - Cedar Labs Dec 2025 - Jan 2026"},
                      {"quote": "• Developed PHP MVC modules with search, filtering, and pagination."}]},
        {"id": "role-2", "field": "experience",
         "value": {"title": "Engineer", "organization": "Pine Works",
                   "period": "Jan 2024 - Nov 2025", "notes": None},
         "evidence": [{"quote": "Engineer - Pine Works Jan 2024 - Nov 2025"}]},
    ]})
    accepted, partial = profile_suggestion_service.validate_output(output, source, salvage_experience=True)
    assert not partial
    assert len(accepted) == 2
    first = accepted[0]
    assert "Wrote MySQL queries" in first["value"]["notes"]
    assert "added reusable validation" in first["value"]["notes"]
    assert "Reduced repeat database queries" in first["value"]["notes"]
    assert "Prepared 2025 reporting exports" in first["value"]["notes"]
    assert "personal demo" not in first["value"]["notes"]
    assert all(quote["quote"] in source for quote in first["evidence"])
    assert accepted[1]["value"]["notes"] == "• Maintained internal Python services."


def test_stale_set_reviews_and_saves_all_fields_with_manual_edits(ready, suggestion_client, db_session):
    owner, _, record, selections = ready
    auth = headers(owner)
    before = {"target_roles": ["Old role"], "remote_preference": "remote", "work_authorization": "other"}
    assert suggestion_client.patch("/api/profile", headers=auth, json=before).status_code == 200
    manual = {"target_roles": ["Full-Stack Developer"], "headline": "Engineer", "remote_preference": "hybrid",
              "work_authorization": "citizen", "salary_preference": {"currency": "USD", "min": 50000, "max": 75000},
              "experience": [{"title": "Developer", "organization": "Manual company", "period": "2020-2024", "notes": "Built APIs"}]}
    payload = {"selections": selections, "manual_fields": manual}
    url = f"/api/profile-suggestions/{record['id']}"
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 409
    review = suggestion_client.post(url + "/review", headers=auth, json=payload)
    assert review.status_code == 200
    preview = review.json()
    original = stored(db_session, owner)
    assert original["skills"] is None and original["languages"] is None
    assert original["target_roles"] == ["Old role"]
    unchanged = db_session.get(ProfileSuggestionSet, uuid.UUID(record["id"]))
    assert unchanged.applied_at is None and unchanged.status == "ready"
    assert record["field_statuses"]["headline"] == "needs_review"
    assert record["field_statuses"]["experience"] == "needs_review"
    assert record["field_statuses"]["target_roles"] == "not_found"
    assert len(record["field_statuses"]) == 10
    payload["reviewed_profile_revision"] = preview["reviewed_profile_revision"]
    response = suggestion_client.post(url + "/apply", headers=auth, json=payload)
    assert response.status_code == 200
    saved = stored(db_session, owner)
    expected = {**manual, "location": "Tripoli", "skills": ["Python", "SQL"],
                "education": [selections[2]["value"], selections[3]["value"]],
                "languages": [{"name": "Arabic", "proficiency": "native"}, {"name": "English", "proficiency": "professional"}]}
    for field, value in expected.items():
        assert saved[field] == value
        assert preview["proposed_profile"][field] == value
        assert response.json()["profile"][field] == value
    assert saved["ai_provenance"]["headline"] == {"origin": "user"}
    assert saved["ai_provenance"]["languages"][0]["origin"] == "ai"
    get = suggestion_client.get("/api/profile", headers=auth).json()
    assert {field: get[field] for field in expected} == expected
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 200
    payload["manual_fields"]["headline"] = "Different"
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 409


def test_manual_only_clear_and_untouched_fields(ready, suggestion_client, db_session):
    owner, _, record, _ = ready
    auth = headers(owner)
    suggestion_client.patch("/api/profile", headers=auth, json={"headline": "Keep", "skills": ["SQL"], "location": "Clear me"})
    url = f"/api/profile-suggestions/{record['id']}"
    payload = {"manual_fields": {"location": None}}
    review = suggestion_client.post(url + "/review", headers=auth, json=payload)
    assert review.status_code == 200
    payload["reviewed_profile_revision"] = review.json()["reviewed_profile_revision"]
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 200
    row = stored(db_session, owner)
    assert row["location"] is None and row["headline"] == "Keep" and row["skills"] == ["SQL"]


def test_revision_conflict_preserves_data_and_can_be_reviewed_again(ready, suggestion_client, db_session):
    owner, _, record, selections = ready
    auth = headers(owner)
    url = f"/api/profile-suggestions/{record['id']}"
    payload = {"selections": selections}
    review = suggestion_client.post(url + "/review", headers=auth, json=payload).json()
    assert stored(db_session, owner) is None
    suggestion_client.patch("/api/profile", headers=auth, json={"headline": "Changed elsewhere"})
    payload["reviewed_profile_revision"] = review["reviewed_profile_revision"]
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 409
    assert stored(db_session, owner)["languages"] is None
    updated = suggestion_client.post(url + "/review", headers=auth, json={"selections": selections}).json()
    payload["reviewed_profile_revision"] = updated["reviewed_profile_revision"]
    assert suggestion_client.post(url + "/apply", headers=auth, json=payload).status_code == 200
    assert stored(db_session, owner)["headline"] == "Changed elsewhere"


@pytest.mark.parametrize("case", ["overlap", "evidence", "changed_field", "empty", "limit", "salary"])
def test_invalid_form_is_atomic_and_identifies_field(ready, suggestion_client, db_session, case):
    owner, _, record, selections = ready
    payload = {"selections": selections, "manual_fields": {"headline": "Must not save"}}
    expected = ""
    if case == "overlap": payload["manual_fields"]["languages"] = []; expected = "languages"
    if case == "evidence": selections[-1]["value"]["name"] = "Unsupported"; expected = "languages"
    if case == "changed_field": selections[0]["field"] = "headline"; payload["manual_fields"] = {}; expected = "field"
    if case == "empty": payload = {"selections": [], "manual_fields": {}}
    if case == "salary": payload["manual_fields"]["salary_preference"] = {"min": 10, "max": 1}
    if case == "limit":
        suggestion_client.patch("/api/profile", headers=headers(owner), json={"skills": [f"Existing {i}" for i in range(50)]})
        expected = "skills"
    url = f"/api/profile-suggestions/{record['id']}"
    result = suggestion_client.post(url + "/review", headers=headers(owner), json=payload)
    assert result.status_code == 422
    if expected: assert expected in result.text
    row = stored(db_session, owner)
    revision = "none" if row is None else row["updated_at"].isoformat()
    result = suggestion_client.post(url + "/apply", headers=headers(owner), json={**payload, "reviewed_profile_revision": revision})
    assert result.status_code == 422
    row = stored(db_session, owner)
    assert row is None or row["headline"] is None
    assert db_session.get(ProfileSuggestionSet, uuid.UUID(record["id"])).applied_at is None


def test_source_change_and_ownership_still_block_review_and_save(ready, suggestion_client, db_session):
    owner, other, record, selections = ready
    url = f"/api/profile-suggestions/{record['id']}"
    payload = {"selections": selections}
    review = suggestion_client.post(url + "/review", headers=headers(owner), json=payload).json()
    for suffix in ["/review", "/apply"]:
        assert suggestion_client.post(url + suffix, headers=headers(other), json=payload).status_code == 404
    suggestion_client.patch(f"/api/resumes/{record['resume_id']}/extraction", headers=headers(owner), json={"draft_text": "Changed source"})
    for suffix in ["/review", "/apply"]:
        data = {**payload, "reviewed_profile_revision": review["reviewed_profile_revision"]} if suffix == "/apply" else payload
        response = suggestion_client.post(url + suffix, headers=headers(owner), json=data)
        assert response.status_code == 409
        assert "CV text changed" in response.text
    assert stored(db_session, owner) is None


def test_unchecked_language_and_duplicate_skills(ready, suggestion_client, db_session):
    owner, _, record, selections = ready
    suggestion_client.patch("/api/profile", headers=headers(owner), json={"skills": ["Python"]})
    selections = selections[:-1]
    url = f"/api/profile-suggestions/{record['id']}"
    review = suggestion_client.post(url + "/review", headers=headers(owner), json={"selections": selections}).json()
    result = suggestion_client.post(url + "/apply", headers=headers(owner), json={"selections": selections, "reviewed_profile_revision": review["reviewed_profile_revision"]})
    assert result.status_code == 200
    row = stored(db_session, owner)
    assert row["skills"] == ["Python", "SQL"]
    assert row["languages"] == [{"name": "Arabic", "proficiency": "native"}]
