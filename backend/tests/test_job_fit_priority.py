"""Mocked job-fit output priority checks; no external provider request."""
from app.schemas.job_fit import CandidateFact, ProviderJobFitOutput
from app.services.job_fit_service import JobFitError, source_job_quote, validate_output
import pytest


def analysis(quote, importance="required", assessment="not_evidenced", skill="Kubernetes"):
    return ProviderJobFitOutput(requirements=[{
        "id": "req-1", "text": skill, "job_quote": quote,
        "importance": importance, "assessment": assessment,
        "explanation": "No saved evidence", "candidate_fact_ids": [], "skill_name": skill,
    }])


def test_unsupported_required_label_becomes_unspecified_without_dropping_the_gap():
    description = "Key Responsibilities: Kubernetes platform work."
    result = validate_output(analysis("Kubernetes platform work"), description, [])
    assert result["requirements"][0]["importance"] == "unspecified"
    assert result["requirements"][0]["assessment"] == "not_evidenced"


def test_basic_and_preferred_sections_establish_priority_for_short_quotes():
    description = "Basic Qualifications: Kubernetes experience. Preferred Skills: Docker experience."
    required = validate_output(analysis("Kubernetes experience"), description, [])
    preferred = validate_output(analysis("Docker experience", skill="Docker"), description, [])
    assert required["requirements"][0]["importance"] == "required"
    assert preferred["requirements"][0]["importance"] == "preferred"


def test_explicit_wording_wins_and_repeated_quote_has_no_section_inference():
    description = "Preferred Skills: Kubernetes required. Basic Qualifications: Kubernetes experience. Additional Qualifications: Kubernetes experience."
    explicit = validate_output(analysis("Kubernetes required", "preferred"), description, [])
    repeated = validate_output(analysis("Kubernetes experience"), description, [])
    assert explicit["requirements"][0]["importance"] == "required"
    assert repeated["requirements"][0]["importance"] == "unspecified"


def test_saved_candidate_evidence_is_still_checked():
    output = analysis("Kubernetes required", assessment="supported")
    output.requirements[0].candidate_fact_ids = ["fact-1"]
    facts = [CandidateFact(id="fact-1", path="skills[0]", value="Kubernetes")]
    assert validate_output(output, "Kubernetes required", facts)["requirements"][0]["assessment"] == "supported"


def test_quote_spacing_and_case_are_recovered_from_exact_source_words():
    description = "Basic Qualifications: • At least 2 years of experience\u00a0 using Python and Git."
    quote = "at least 2 years of experience using python and git"
    result = validate_output(analysis(quote, skill="Python"), description, [])
    assert result["requirements"][0]["job_quote"] == "At least 2 years of experience\u00a0 using Python and Git"
    assert result["requirements"][0]["importance"] == "required"


def test_reworded_or_ambiguous_quote_stays_rejected():
    description = "Python required. Python required."
    assert source_job_quote("python required", description) is None
    with pytest.raises(JobFitError, match="no verifiable job requirements"):
        validate_output(analysis("Python required with Kubernetes"), description, [])


def test_named_skill_uses_source_clause_when_ai_paraphrases():
    description = "Basic Qualifications: • At least 2 years of experience using Python and Git."
    result = validate_output(analysis("Python development experience required", skill="Python"), description, [])
    item = result["requirements"][0]
    assert item["job_quote"] == "At least 2 years of experience using Python and Git."
    assert item["text"] == "Python"
    assert item["importance"] == "required"
    assert "Only requirements verified" in result["summary"]


def test_one_unverifiable_requirement_does_not_erase_verified_fit():
    output = ProviderJobFitOutput(requirements=[
        analysis("Python required", skill="Python").requirements[0],
        {"id": "req-2", "text": "Invented skill", "job_quote": "Invented skill required",
         "importance": "required", "assessment": "not_evidenced", "explanation": "No evidence",
         "candidate_fact_ids": [], "skill_name": "Invented skill"},
    ], gaps=["req-1: Python gap", "req-2: Invented gap"], summary="Invented summary")
    result = validate_output(output, "Python required", [])
    assert [item["id"] for item in result["requirements"]] == ["req-1"]
    assert result["gaps"] == ["req-1: Python gap"]
    assert "Invented" not in result["summary"]
