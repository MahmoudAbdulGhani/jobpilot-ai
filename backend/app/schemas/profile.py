import uuid
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

HEADLINE_MAX_LENGTH = 200
LOCATION_MAX_LENGTH = 300
ROLE_MAX_LENGTH = 200
MAX_TARGET_ROLES = 10
SKILL_MAX_LENGTH = 100
MAX_SKILLS = 50
MAX_EXPERIENCE_ENTRIES = 20
MAX_EDUCATION_ENTRIES = 10
MAX_LANGUAGES = 15
ENTRY_TITLE_MAX_LENGTH = 200
ORGANIZATION_MAX_LENGTH = 200
PERIOD_MAX_LENGTH = 100
ENTRY_NOTES_MAX_LENGTH = 2_000
CURRENCY_MAX_LENGTH = 12

REMOTE_PREFERENCES = Literal["office", "hybrid", "remote"]
WORK_AUTHORIZATIONS = Literal[
    "citizen",
    "permanent_resident",
    "work_visa",
    "needs_sponsorship",
    "other",
]
LANGUAGE_PROFICIENCIES = Literal["basic", "conversational", "professional", "native"]


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str = Field(
        validation_alias=AliasChoices("title", "job_title"),
        min_length=1,
        max_length=ENTRY_TITLE_MAX_LENGTH,
    )
    organization: str = Field(min_length=1, max_length=ORGANIZATION_MAX_LENGTH)
    period: str | None = Field(default=None, max_length=PERIOD_MAX_LENGTH)
    notes: str | None = Field(default=None, max_length=ENTRY_NOTES_MAX_LENGTH)


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school: str = Field(min_length=1, max_length=ENTRY_TITLE_MAX_LENGTH)
    degree: str | None = Field(default=None, max_length=ENTRY_TITLE_MAX_LENGTH)
    field: str | None = Field(default=None, max_length=ENTRY_TITLE_MAX_LENGTH)
    period: str | None = Field(default=None, max_length=PERIOD_MAX_LENGTH)


class LanguageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    proficiency: LANGUAGE_PROFICIENCIES


class SalaryPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(default="USD", min_length=1, max_length=CURRENCY_MAX_LENGTH)
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def minimum_must_not_exceed_maximum(self) -> "SalaryPreference":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("minimum salary must not exceed maximum salary")
        return self


class CandidateProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str | None = Field(default=None, max_length=HEADLINE_MAX_LENGTH)
    target_roles: list[str] | None = Field(default=None, max_length=MAX_TARGET_ROLES)
    location: str | None = Field(default=None, max_length=LOCATION_MAX_LENGTH)
    remote_preference: REMOTE_PREFERENCES | None = None
    work_authorization: WORK_AUTHORIZATIONS | None = None
    skills: list[str] | None = Field(default=None, max_length=MAX_SKILLS)
    experience: list[ExperienceEntry] | None = Field(
        default=None, max_length=MAX_EXPERIENCE_ENTRIES
    )
    education: list[EducationEntry] | None = Field(
        default=None, max_length=MAX_EDUCATION_ENTRIES
    )
    languages: list[LanguageEntry] | None = Field(
        default=None, max_length=MAX_LANGUAGES
    )
    salary_preference: SalaryPreference | None = None

    @field_validator("headline", "location")
    @classmethod
    def normalize_optional_short_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("target_roles", "skills")
    @classmethod
    def normalize_string_lists(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = []
        for item in value:
            cleaned = item.strip()
            if not cleaned:
                raise ValueError("list entries must not be blank")
            normalized.append(cleaned)
        return normalized

    @field_validator("target_roles")
    @classmethod
    def limit_target_role_length(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for item in value:
            if len(item) > ROLE_MAX_LENGTH:
                raise ValueError("target roles must be 200 characters or fewer")
        return value

    @field_validator("skills")
    @classmethod
    def limit_skill_length(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        for item in value:
            if len(item) > SKILL_MAX_LENGTH:
                raise ValueError("skills must be 100 characters or fewer")
        return value


class CandidateProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    headline: str | None
    target_roles: list[str] | None
    location: str | None
    remote_preference: REMOTE_PREFERENCES | None
    work_authorization: WORK_AUTHORIZATIONS | None
    skills: list[str] | None
    experience: list[ExperienceEntry] | None
    education: list[EducationEntry] | None
    languages: list[LanguageEntry] | None
    salary_preference: SalaryPreference | None
    created_at: datetime
    updated_at: datetime