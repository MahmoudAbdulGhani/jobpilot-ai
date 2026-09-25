import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

Importance = Literal["required", "preferred", "unspecified"]
Assessment = Literal[
    "supported", "partially_supported", "not_evidenced",
    "needs_clarification", "explicit_mismatch",
]


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^fact-[0-9]+$", max_length=30)
    path: str = Field(max_length=100)
    value: str = Field(min_length=1, max_length=2_000)


class ProviderRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^req-[0-9]+$", max_length=30)
    text: str = Field(min_length=1, max_length=500)
    job_quote: str = Field(min_length=1, max_length=1_000)
    importance: Importance
    assessment: Assessment
    explanation: str = Field(min_length=1, max_length=1_000)
    candidate_fact_ids: list[str] = Field(default_factory=list, max_length=20)
    skill_name: str | None = Field(default=None, min_length=1, max_length=100)


class ProviderJobFitOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[ProviderRequirement] = Field(max_length=50)
    strengths: list[str] = Field(default_factory=list, max_length=20)
    gaps: list[str] = Field(default_factory=list, max_length=20)
    actions: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(default="", max_length=2_000)

    @property
    def missing_skills(self) -> list[dict[str, str]]:
        return [{"skill": item.skill_name, "requirement_id": item.id,
                 "job_quote": item.job_quote, "importance": item.importance}
                for item in self.requirements
                if item.skill_name and item.assessment == "not_evidenced"
                and item.importance in {"required", "preferred"}]

    @model_validator(mode="after")
    def references_known_requirements(self):
        ids = {item.id for item in self.requirements}
        if len(ids) != len(self.requirements):
            raise ValueError("requirement IDs must be unique")
        for items in (self.strengths, self.gaps, self.actions):
            if any(not item.startswith(tuple(f"{key}:" for key in ids)) for item in items):
                raise ValueError("narrative items must begin with a requirement ID")
        return self


class JobFitResultResponse(ProviderJobFitOutput):
    @computed_field
    @property
    def missing_skills(self) -> list[dict[str, str]]:
        return super().missing_skills


class JobFitGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class JobFitAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    job_snapshot: dict
    profile_facts: list[CandidateFact]
    result: JobFitResultResponse | None
    counts: dict[str, int]
    provider: str
    model: str
    prompt_version: str
    outcome_message: str | None
    is_outdated: bool = False
    created_at: datetime
    updated_at: datetime


class JobFitAnalysisList(BaseModel):
    items: list[JobFitAnalysisResponse]
    total: int
    page: int
    page_size: int
