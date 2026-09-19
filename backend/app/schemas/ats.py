import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AtsCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    status: str
    detail: str
    evidence: list[str]


class AtsReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pack_version: int | None = None


class AtsReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    pack_id: uuid.UUID
    pack_version: int
    checks: list[AtsCheck]
    readiness_score: int
    report_version: str
    created_at: datetime
    updated_at: datetime


class AtsReportList(BaseModel):
    items: list[AtsReportResponse]
    total: int
    page: int
    page_size: int


class AtsImproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(
        min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class AtsImproveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: uuid.UUID
    job_id: uuid.UUID
    pack_id: uuid.UUID
    approved_version: int
    version_number: int
    review_notes: list[str]
    preview_checks: list[AtsCheck]
    preview_readiness: int
