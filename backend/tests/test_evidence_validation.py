"""Adversarial evidence regressions, entirely local."""
import pytest

from app.services.evidence_validation import supported_claim
from app.services.application_pack_service import validate_generated, PackError
from app.services.ai_provider import DeterministicTestProvider
from app.evaluation.fixtures import cases


@pytest.mark.parametrize("claim,passages", [
    ("Python and Kubernetes", ["Python"]),
    ("Increased revenue by 50%", ["Increased revenue by 5%"]),
    ("Python", ["Python", "French"]),
    ("I worked with Python", ["Python"]),
    ("I have 5 years experience", ["5 projects"]),
    ("Led Python projects", ["Never led Python projects"]),
    ("Engineer at Acme", ["Engineer", "Acme"]),
])
def test_unsupported_claims_numbers_irrelevant_citations_and_experience(claim, passages):
    assert not supported_claim(claim, passages)


@pytest.mark.parametrize("claim", ["Invented employer", "Delivered 999 projects"])
def test_pack_rejects_fabrications_even_with_authentic_quote(claim):
    source = cases()[0]["source"]
    output = DeterministicTestProvider().create_pack(source).model_dump(mode="json")
    block = next(b for b in output["cv"]["blocks"] if b["kind"] != "heading")
    block["text"] = claim
    with pytest.raises(PackError, match="not supported"):
        validate_generated(output, source)
