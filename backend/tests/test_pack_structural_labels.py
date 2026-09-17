"""Offline structural regressions; no provider request or inferred evidence."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider
from app.services.application_pack_service import validate_generated, PackError


def documents():
    source = cases()[0]["source"]
    return source, DeterministicTestProvider().create_pack(source).model_dump(mode="json")


def label(text, block_id="label"):
    return {"id": block_id, "kind": "paragraph", "text": text, "evidence": []}


def test_observed_labels_corrected_without_changing_claims_or_evidence():
    source, output = documents()
    # Recovered label strings, in a synthetic surrogate: original unredacted
    # full live output was not retained and is not reconstructed here.
    output["cv"]["blocks"].insert(1, label("Contact", "contact-label"))
    output["cover_letter"]["blocks"].insert(1, label("Application for Backend Engineer", "subject"))
    original = deepcopy(output)
    expected = deepcopy(output)
    expected["cv"]["blocks"][1]["kind"] = "heading"
    expected["cover_letter"]["blocks"].pop(1)
    assert validate_generated(output, source).model_dump(mode="json") == expected
    assert output == original


@pytest.mark.parametrize("text", ["Contact me at invented@example.test", "Contact: CEO", "Python", "I built the API using Python.", "Application for Backend Engineer; I have a PhD", "Application for Chief Executive", "Thank you."])
def test_arbitrary_short_or_prefixed_body_text_still_requires_evidence(text):
    source, output = documents()
    output["cover_letter"]["blocks"].append(label(text))
    with pytest.raises(PackError, match="missing source evidence"):
        validate_generated(output, source)


def test_context_label_without_matching_heading_is_not_removed():
    source, output = documents()
    output["cover_letter"]["blocks"] = [label("Application for Backend Engineer")]
    with pytest.raises(PackError, match="missing source evidence"):
        validate_generated(output, source)


def test_removing_subject_cannot_make_heading_only_letter_pass():
    source, output = documents()
    output["cover_letter"]["blocks"] = [output["cover_letter"]["blocks"][0], label("Application for Backend Engineer")]
    with pytest.raises(ValidationError, match="body text"):
        validate_generated(output, source)


def test_classified_heading_still_cannot_contain_factual_claim():
    source, output = documents()
    output["cv"]["blocks"].append(dict(label("Contact: CEO"), kind="heading"))
    with pytest.raises(PackError, match="unsupported heading"):
        validate_generated(output, source)


def test_structural_correction_does_not_hide_invalid_evidence():
    source, output = documents()
    bad = label("Contact")
    bad["evidence"] = [{"fact_id": None, "cv_quote": "invented quote"}]
    output["cv"]["blocks"].append(bad)
    with pytest.raises(PackError, match="unsupported CV passage"):
        validate_generated(output, source)
