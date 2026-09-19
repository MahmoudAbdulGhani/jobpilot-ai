import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
