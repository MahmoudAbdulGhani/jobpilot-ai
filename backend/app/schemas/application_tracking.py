import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

ApplicationMethod = Literal["email",
                            "employer_website", "linkedin_manual", "other"]
ApplicationStatus = Literal["Applied",
                            "Interview", "Offer", "Accepted", "Rejected", "Withdrawn"]


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID | None = None
    submission_date: datetime
    method: ApplicationMethod
    notes: str | None = None
    follow_up_date: AwareDatetime | None = None
    pack_id: uuid.UUID | None = None
    pack_version: int | None = None
    status: ApplicationStatus = "Applied"

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            return value or None
        return value


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_date: datetime | None = None
    method: ApplicationMethod | None = None
    notes: str | None = None
    follow_up_date: AwareDatetime | None = None
    status: ApplicationStatus | None = None
    pack_id: uuid.UUID | None = None
    pack_version: int | None = None


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    job_id: uuid.UUID
    submission_date: datetime
    method: str
    notes: str | None
    status: str
    origin: str
    follow_up_date: datetime | None
    reminder_status: str | None
    reminder_timezone: str | None
    pack_id: uuid.UUID | None
    pack_version: int | None
    cv_snapshot: dict[str, Any] | None
    cover_letter_snapshot: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ApplicationStatusEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    status: str
    changed_at: datetime
    created_at: datetime
    updated_at: datetime


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    kind: Literal["submitted", "status", "reply", "followup", "email"]
    title: str
    detail: str | None = None
    evidence: list[str] = Field(default_factory=list)


class ApplicationTimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: uuid.UUID
    job_id: uuid.UUID
    narrative: str
    entries: list[TimelineEntry]
    total: int


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int
    page_size: int
