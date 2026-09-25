"""Offline checks for a rejected AI sentence; no external provider call."""
from copy import deepcopy

import pytest

from app.evaluation.fixtures import cases
from app.services.ai_provider import DeterministicTestProvider
from app.services.application_pack_service import (
    PackError, UnsupportedPackClaim, repair_unsupported_claims, validate_generated,
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
