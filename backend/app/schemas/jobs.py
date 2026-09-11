import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

TITLE_MAX_LENGTH = 200
COMPANY_MAX_LENGTH = 200
LOCATION_MAX_LENGTH = 300
DESCRIPTION_MAX_LENGTH = 50_000
SOURCE_URL_MAX_LENGTH = 2_048
NOTES_MAX_LENGTH = 20_000
SEARCH_MAX_LENGTH = 200
MAX_PAGE_SIZE = 100


class _JobFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    company: str = Field(min_length=1, max_length=COMPANY_MAX_LENGTH)
    location: str | None = Field(default=None, max_length=LOCATION_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    source_url: HttpUrl | None = Field(default=None, max_length=SOURCE_URL_MAX_LENGTH)
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)
    is_archived: bool = False

    @field_validator("title", "company")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("location")
    @classmethod
    def normalize_optional_short_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class SavedJobCreate(_JobFields):
    pass


class SavedJobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    company: str | None = Field(default=None, min_length=1, max_length=COMPANY_MAX_LENGTH)
    location: str | None = Field(default=None, max_length=LOCATION_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    source_url: HttpUrl | None = Field(default=None, max_length=SOURCE_URL_MAX_LENGTH)
    notes: str | None = Field(default=None, max_length=NOTES_MAX_LENGTH)
    is_archived: bool | None = None

    @field_validator("title", "company")
    @classmethod
    def validate_required_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("must not be null")
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("location")
    @classmethod
    def normalize_optional_short_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("is_archived")
    @classmethod
    def archive_must_not_be_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("must not be null")
        return value


class SavedJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    company: str
    location: str | None
    description: str | None
    source_url: str | None
    notes: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class SavedJobListResponse(BaseModel):
    items: list[SavedJobResponse]
    total: int
    page: int
    page_size: int
