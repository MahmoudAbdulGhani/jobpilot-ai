import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SuggestionField = Literal["headline", "location", "skills", "experience", "education", "languages"]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(min_length=1, max_length=1000)


class ProfileSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    field: SuggestionField
    value: Any
    evidence: list[Evidence] = Field(min_length=1, max_length=10)


class ProviderSuggestionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suggestions: list[ProfileSuggestion] = Field(max_length=50)
    partial: bool = False
    message: str | None = Field(default=None, max_length=500)


class SuggestionSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    resume_id: uuid.UUID
    source_hash: str
    source_reviewed_at: datetime
    profile_revision: str
    status: str
    suggestions: list[dict[str, Any]] | None
    provider: str
    model: str
    prompt_version: str
    outcome_message: str | None
    applied_at: datetime | None
    apply_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ApplySuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selections: list[ProfileSuggestion] = Field(min_length=1, max_length=50)
