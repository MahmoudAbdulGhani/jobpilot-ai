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