from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DigestCadence = Literal["off", "daily", "weekly"]


class DigestPreferences(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cadence: str
    updated_at: datetime


class DigestCadenceChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cadence: DigestCadence
    confirm: Literal[True]


class DigestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    external_id: str
    title: str
    company: str
    location: str | None
    source_url: str
    published_at: str | None
    salary: str | None
    workplace_model: str | None
    applicant_region: str | None
    remote_arrangement: str
    test_data: bool
    refreshed_at: datetime | None


class DigestDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    reason: str


class DigestPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generated_at: datetime
    cadence: str
    items: list[DigestItem]
    skipped_invalid: int
    delivery: DigestDelivery
