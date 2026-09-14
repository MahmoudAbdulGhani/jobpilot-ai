import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISPLAY_NAME_MAX_LENGTH = 255


class ResumeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(
        default=None, min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH
    )
    is_primary: bool | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("display name must not be blank")
        return value


class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    original_filename: str
    display_name: str
    file_extension: str
    size_bytes: int
    is_primary: bool
    created_at: datetime
    updated_at: datetime


class ResumeListResponse(BaseModel):
    items: list[ResumeResponse]


class ResumeExtractionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_text: str = Field(min_length=1)

    @field_validator("draft_text")
    @classmethod
    def reject_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("extracted text must not be blank")
        return value


class ResumeExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    status: str
    original_text: str | None
    draft_text: str | None
    parser_name: str | None
    parser_version: str | None
    failure_code: str | None
    failure_message: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
