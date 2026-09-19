import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ClassificationConfirm = Literal[True]
ApplicationStatusValue = Literal["Applied", "Interview", "Offer", "Accepted", "Rejected", "Withdrawn"]


class ClassificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reply_id: uuid.UUID
    category: str
    confidence: int
    evidence_excerpt: str
    uncertainty: str
    suggested_status: str | None
    status_applied: bool
    applied_status: str | None
    created_at: datetime
    updated_at: datetime


class ClassificationConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: ClassificationConfirm
    status: ApplicationStatusValue
