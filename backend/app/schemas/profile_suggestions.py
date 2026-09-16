import uuid
from datetime import datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import (
    ENTRY_TITLE_MAX_LENGTH,
    EducationEntry,
    HEADLINE_MAX_LENGTH,
    LOCATION_MAX_LENGTH,
    LanguageEntry,
    ExperienceEntry,
    SKILL_MAX_LENGTH,
)

SuggestionField = Literal["headline", "location", "skills", "experience", "education", "languages"]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(min_length=1, max_length=1000)


class _SuggestionShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    evidence: list[Evidence] = Field(min_length=1, max_length=10)


class HeadlineSuggestion(_SuggestionShape):
    field: Literal["headline"]
    value: str = Field(min_length=1, max_length=HEADLINE_MAX_LENGTH)


class LocationSuggestion(_SuggestionShape):
    field: Literal["location"]
    value: str = Field(min_length=1, max_length=LOCATION_MAX_LENGTH)


class SkillsSuggestion(_SuggestionShape):
    field: Literal["skills"]
    value: str = Field(min_length=1, max_length=SKILL_MAX_LENGTH)


class ExperienceSuggestion(_SuggestionShape):
    field: Literal["experience"]
    value: ExperienceEntry


class EducationSuggestion(_SuggestionShape):
    field: Literal["education"]
    value: EducationEntry


class LanguageSuggestion(_SuggestionShape):
    field: Literal["languages"]
    value: LanguageEntry


# Untagged union on purpose: pydantic emits ``anyOf`` in the provider JSON
# schema (the SDK's strict converter and compatible Responses endpoints handle
# ``anyOf``, not ``oneOf``/``discriminator``). The disjoint ``field`` literals
# make the parse deterministic while the schema now constrains each field's
# ``value`` to the shape the production validator accepts.
ProfileSuggestion = Union[
    HeadlineSuggestion,
    LocationSuggestion,
    SkillsSuggestion,
    ExperienceSuggestion,
    EducationSuggestion,
    LanguageSuggestion,
]


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
