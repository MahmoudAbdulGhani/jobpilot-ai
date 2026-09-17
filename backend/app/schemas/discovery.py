"""Bounded, plain-text discovery contract. No client-supplied provider URLs."""
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.jobs import SavedJobResponse

ExternalId = Annotated[str, Field(pattern=r"^[0-9A-Za-z_-]{1,128}$")]


class DiscoveryJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["jobtech"] = "jobtech"
    external_id: ExternalId
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=50_000)
    source_url: str = Field(max_length=2048)
    published_at: str | None = None
    deadline: str | None = None
    salary: str | None = Field(default=None, max_length=2000)
    workplace_model: str | None = Field(default=None, max_length=300)
    test_data: bool = False

    @field_validator("title", "company")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Required source field is blank")
        return value.strip()

    @field_validator("published_at", "deadline")
    @classmethod
    def source_date(cls, value):
        if value is not None:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class DiscoveryResult(DiscoveryJob):
    existing_job_id: uuid.UUID | None = None


class DiscoverySearch(BaseModel):
    items: list[DiscoveryResult]
    total: int
    offset: int
    next_offset: int | None


class DiscoveryPreview(BaseModel):
    job: DiscoveryResult
    preview_token: str
    expires_at: datetime


class DiscoveryImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_token: str = Field(min_length=1, max_length=1_000_000)
    confirm: Literal[True]


class DiscoveryImported(BaseModel):
    job: SavedJobResponse
    already_saved: bool
