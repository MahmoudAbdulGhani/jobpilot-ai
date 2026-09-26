"""Offline checks for a rejected AI sentence; no external provider call."""
from copy import deepcopy

import pytest

from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider
from app.services.application_pack_service import (
    PackError, UnsupportedPackClaim, include_confirmed_job_skills,
    canonical_cv_quotes, salvage_generated, validate_generated,
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

    repaired = salvage_generated(output, source)
    checked = validate_generated(repaired, source)
    assert checked.cv.blocks[1].text == original_quote
    assert checked.cv.blocks[1].evidence[0].cv_quote == original_quote
    assert checked.cv.blocks[2].model_dump(mode="json") == untouched
    assert "rewritten from one exact CV passage" in checked.review_notes[-1]
    assert output["cv"]["blocks"][1]["text"] == "Accomplished professional Alex Example"


def test_formatted_cv_quote_recovers_unique_exact_span_without_changing_source():
    source, output = draft()
    source["cv_text"] = source["cv_text"].replace(
        "Engineer at Cedar Demo, 2021-2024", "Engineer   at Cedar Demo, 2021–2024")
    block = next(block for block in output["cv"]["blocks"] if "Engineer at Cedar" in block["text"])
    block["text"] = "Engineer at Cedar Demo, 2021-2024"
    quote = block["evidence"][0]
    assert quote["cv_quote"] not in source["cv_text"]
    original = deepcopy(output)
    with pytest.raises(PackError, match="unsupported CV passage"):
        validate_generated(output, source)
    checked = validate_generated(canonical_cv_quotes(output, source), source)
    assert next(block for block in checked.cv.blocks if block.text.startswith("Engineer at Cedar")).evidence[0].cv_quote == "Engineer   at Cedar Demo, 2021–2024"
    assert "matched to exact passages" in checked.review_notes[-1]
    assert output == original


def test_cv_quote_recovery_rejects_changed_words_and_ambiguous_matches():
    source, output = draft()
    output["cv"]["blocks"][1]["evidence"][0]["cv_quote"] = "Invented Example"
    with pytest.raises(PackError, match="unsupported CV passage"):
        validate_generated(canonical_cv_quotes(output, source), source)

    source, output = draft()
    source["cv_text"] += "\nBackend   engineer\nBackend engineer"
    output["cv"]["blocks"][1]["evidence"][0]["cv_quote"] = "Backend  engineer"
    with pytest.raises(PackError, match="unsupported CV passage"):
        validate_generated(canonical_cv_quotes(output, source), source)


def test_cover_letter_repair_does_not_hide_invented_relation():
    source, output = draft()
    block = output["cover_letter"]["blocks"][1]
    block["text"] = "I built Kubernetes systems with Python"
    checked = validate_generated(salvage_generated(output, source), source)
    assert all("Kubernetes" not in block.text for block in checked.cover_letter.blocks)
    assert "1 cover-letter statement(s) were omitted" in checked.review_notes[-1]


def test_invalid_citation_is_omitted_from_recoverable_draft():
    source, output = draft()
    block = output["cv"]["blocks"][1]
    block["text"] = "Invented employer"
    block["evidence"] = [{"fact_id": None, "cv_quote": "Invented employer"}]
    checked = validate_generated(salvage_generated(output, source), source)
    assert all("Invented employer" not in block.text for block in checked.cv.blocks)
    assert "1 CV" in checked.review_notes[-1]


def test_repair_cannot_discard_bad_citation_beside_valid_one():
    source, output = draft()
    block = output["cv"]["blocks"][1]
    block["text"] = "Invented employer"
    block["evidence"].append({"fact_id": "fact-999", "cv_quote": None})
    checked = validate_generated(salvage_generated(output, source), source)
    assert all("Invented employer" not in block.text for block in checked.cv.blocks)


def test_unsupported_claim_without_usable_source_is_omitted():
    source, output = draft()
    block = output["cv"]["blocks"][1]
    block["text"] = "Invented employer"
    block["evidence"] = []
    checked = validate_generated(salvage_generated(output, source), source)
    assert all("Invented employer" not in block.text for block in checked.cv.blocks)


def test_multiple_unsafe_blocks_and_empty_section_are_removed():
    source, output = draft()
    blocks = output["cv"]["blocks"]
    blocks.insert(2, {"id": "empty-section", "kind": "heading", "text": "Projects", "evidence": []})
    blocks.insert(3, {"id": "false-project", "kind": "bullet", "text": "Built an unrelated project",
                      "evidence": [{"fact_id": None, "cv_quote": "Made-up CV line"}]})
    blocks.insert(4, {"id": "next-section", "kind": "heading", "text": "Experience", "evidence": []})
    blocks.insert(5, {"id": "false-experience", "kind": "bullet", "text": "Led a fictional team",
                      "evidence": [{"fact_id": "fact-999", "cv_quote": None}]})
    checked = validate_generated(salvage_generated(output, source), source)
    texts = [block.text for block in checked.cv.blocks]
    assert "Projects" not in texts and texts.count("Experience") == 1
    assert "Built an unrelated project" not in texts and "Led a fictional team" not in texts
    assert "2 CV" in checked.review_notes[-1]


@pytest.mark.parametrize("document, label", [("cv", "CV"), ("cover_letter", "cover letter")])
def test_insufficient_supported_document_has_specific_content_free_failure(document, label):
    source, output = draft()
    for block in output[document]["blocks"]:
        if block["kind"] != "heading":
            block["evidence"] = [{"fact_id": "fact-999", "cv_quote": None}]
    with pytest.raises(PackError, match=f"not retain enough supported {label} content"):
        salvage_generated(output, source)


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


def test_required_application_skills_take_priority_in_cover_letter():
    source, output = draft()
    source["application_skills"] = [
        {"skill": "Docker", "importance": "preferred"},
        {"skill": "Kubernetes", "importance": "required"},
        {"skill": "Terraform", "importance": "required"},
    ]
    source["application_skill_facts"] = [
        {"id": f"fact-{len(source['profile_facts']) + index + 1}", "path": f"application_skills[{index}]", "value": skill["skill"]}
        for index, skill in enumerate(source["application_skills"])
    ]
    checked = validate_generated(include_confirmed_job_skills(validate_generated(output, source), source), source)
    cv_text = " ".join(block.text for block in checked.cv.blocks)
    letter_text = " ".join(block.text for block in checked.cover_letter.blocks)
    assert all(skill in cv_text for skill in ("Docker", "Kubernetes", "Terraform"))
    assert "Kubernetes" in letter_text and "Terraform" in letter_text
    assert "Docker" not in letter_text


def test_self_attested_skill_cannot_support_invented_project_experience():
    source, output = draft()
    source["application_skill_facts"] = [{"id": "fact-6", "path": "application_skills[0]", "value": "Kubernetes"}]
    output["cv"]["blocks"][1] = {"id": "false-experience", "kind": "bullet",
        "text": "Built Kubernetes systems at Acme", "evidence": [{"fact_id": "fact-6", "cv_quote": None}]}
    with pytest.raises(UnsupportedPackClaim):
        validate_generated(output, source)


def test_separate_skill_and_project_citations_cannot_create_a_relationship():
    source, output = draft()
    source["application_skill_facts"] = [{"id": "fact-6", "path": "application_skills[0]", "value": "Kubernetes"}]
    source["cv_text"] += "\nBooking Project"
    output["cv"]["blocks"][1] = {"id": "false-project-skill", "kind": "bullet",
        "text": "Used Kubernetes on Booking Project",
        "evidence": [{"fact_id": "fact-6", "cv_quote": None},
                     {"fact_id": None, "cv_quote": "Booking Project"}]}
    with pytest.raises(UnsupportedPackClaim):
        validate_generated(output, source)
    checked = validate_generated(salvage_generated(output, source), source)
    assert all("Used Kubernetes on Booking Project" != block.text for block in checked.cv.blocks)


def test_legacy_pack_hash_is_stable_until_job_only_skills_are_selected():
    source = {"job": {"description": "Kubernetes required"}, "profile_id": "profile-1",
              "profile": {"skills": ["Python"]}, "resume_id": "resume-1",
              "extraction_id": "extraction-1", "cv_text": "Python"}
    old_hash = source_hash(source)
    assert source_hash({**source, "application_skills": []}) == old_hash
    assert source_hash({**source, "application_skills": [{"skill": "Kubernetes"}]}) != old_hash
