"""Offline checks for a rejected AI sentence; no external provider call."""
from copy import deepcopy

import pytest

from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider
from app.services.application_pack_service import (
    PackError, UnsupportedPackClaim, include_confirmed_job_skills,
    repair_unsupported_claims, validate_generated,
    source_hash,
)


def draft():
    source = cases()[0]["source"]
    output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
    return source, output


def test_reworded_claim_uses_exact_cited_cv_text_and_keeps_supported_blocks():
    source, output = draft()
    block = output["cv"]["blocks"][1]
    original_quote = block["text"]
    block["text"] = "Accomplished professional Alex Example"
    untouched = deepcopy(output["cv"]["blocks"][2])
    with pytest.raises(UnsupportedPackClaim):
        validate_generated(output, source)

    repaired = repair_unsupported_claims(output, source)
    checked = validate_generated(repaired, source)
    assert checked.cv.blocks[1].text == original_quote
    assert checked.cv.blocks[1].evidence[0].cv_quote == original_quote
    assert checked.cv.blocks[2].model_dump(mode="json") == untouched
    assert "exact cited source text" in checked.review_notes[-1]
    assert output["cv"]["blocks"][1]["text"] == "Accomplished professional Alex Example"


def test_cover_letter_repair_uses_saved_fact_without_inventing_relation():
    source, output = draft()
    block = output["cover_letter"]["blocks"][1]
    block["text"] = "I built Kubernetes systems with Python"
    checked = validate_generated(repair_unsupported_claims(output, source), source)
    assert checked.cover_letter.blocks[1].text == source["profile_facts"][0]["value"]
    assert checked.cover_letter.blocks[1].evidence[0].fact_id == "fact-1"
    assert "Kubernetes" not in checked.cover_letter.blocks[1].text


def test_invalid_citation_is_not_repaired_or_accepted():
    source, output = draft()
    block = output["cv"]["blocks"][1]
    block["text"] = "Invented employer"
    block["evidence"] = [{"fact_id": None, "cv_quote": "Invented employer"}]
    with pytest.raises(PackError, match="unsupported CV passage"):
        validate_generated(repair_unsupported_claims(output, source), source)


def test_unsupported_claim_without_usable_source_still_fails():
    source, output = draft()
    block = output["cv"]["blocks"][1]
    block["text"] = "Invented employer"
    block["evidence"] = []
    with pytest.raises(PackError, match="missing source evidence"):
        validate_generated(repair_unsupported_claims(output, source), source)


def test_job_relevant_confirmed_skill_is_in_both_documents_with_fact_evidence():
    source, output = draft()
    source["job"]["description"] = "Python and Kubernetes are required."
    source["profile_facts"].append({"id": "fact-6", "path": "skills[2]", "value": "Kubernetes"})
    enhanced = include_confirmed_job_skills(validate_generated(output, source), source)
    checked = validate_generated(enhanced, source)
    for document in (checked.cv, checked.cover_letter):
        matching = [block for block in document.blocks if "Kubernetes" in block.text]
        assert matching
        assert any(ref.fact_id == "fact-6" for block in matching for ref in block.evidence)
    cv_blocks = checked.cv.blocks
    skills_heading = next(index for index, block in enumerate(cv_blocks) if block.kind == "heading" and block.text == "Skills")
    assert cv_blocks[skills_heading + 1].kind == "bullet"
    assert "Kubernetes" in cv_blocks[skills_heading + 1].text
    assert any(block.kind == "paragraph" and "I bring Kubernetes to this role." in block.text
               for block in checked.cover_letter.blocks)
    assert "included as sourced statements" in checked.review_notes[-1]


def test_job_skill_matching_uses_word_boundaries():
    source, output = draft()
    source["job"]["description"] = "PostgreSQL required."
    source["profile_facts"].append({"id": "fact-6", "path": "skills[2]", "value": "SQL"})
    enhanced = include_confirmed_job_skills(validate_generated(output, source), source)
    assert not any("I bring SQL to this role." == block.text for block in enhanced.cover_letter.blocks)


def test_unconfirmed_job_requirement_is_not_added_to_documents():
    source, output = draft()
    source["job"]["description"] = "Kubernetes is required."
    enhanced = include_confirmed_job_skills(validate_generated(output, source), source)
    assert all("Kubernetes" not in block.text for document in (enhanced.cv, enhanced.cover_letter)
               for block in document.blocks)


def test_job_only_confirmed_skill_is_cited_without_changing_profile_or_cv():
    source, output = draft()
    old_profile = deepcopy(source["profile_facts"])
    old_cv = source["cv_text"]
    source["application_skill_facts"] = [{"id": "fact-6", "path": "application_skills[0]", "value": "Kubernetes"}]
    source["application_skills"] = [{"id": "selection-1", "skill": "Kubernetes", "importance": "required"}]
    enhanced = include_confirmed_job_skills(validate_generated(output, source), source)
    checked = validate_generated(enhanced, source)
    assert any(block.kind == "bullet" and "Kubernetes" in block.text and
               any(ref.fact_id == "fact-6" for ref in block.evidence) for block in checked.cv.blocks)
    assert any("Kubernetes" in block.text and any(ref.fact_id == "fact-6" for ref in block.evidence)
               for block in checked.cover_letter.blocks)
    assert source["profile_facts"] == old_profile and source["cv_text"] == old_cv


def test_self_attested_skill_cannot_support_invented_project_experience():
    source, output = draft()
    source["application_skill_facts"] = [{"id": "fact-6", "path": "application_skills[0]", "value": "Kubernetes"}]
    output["cv"]["blocks"][1] = {"id": "false-experience", "kind": "bullet",
        "text": "Built Kubernetes systems at Acme", "evidence": [{"fact_id": "fact-6", "cv_quote": None}]}
    with pytest.raises(UnsupportedPackClaim):
        validate_generated(output, source)


def test_legacy_pack_hash_is_stable_until_job_only_skills_are_selected():
    source = {"job": {"description": "Kubernetes required"}, "profile_id": "profile-1",
              "profile": {"skills": ["Python"]}, "resume_id": "resume-1",
              "extraction_id": "extraction-1", "cv_text": "Python"}
    old_hash = source_hash(source)
    assert source_hash({**source, "application_skills": []}) == old_hash
    assert source_hash({**source, "application_skills": [{"skill": "Kubernetes"}]}) != old_hash
