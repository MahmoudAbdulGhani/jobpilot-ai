"""Mocked job-fit output priority checks; no external provider request."""
from app.schemas.job_fit import CandidateFact, ProviderJobFitOutput
from app.services.job_fit_service import validate_output


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
