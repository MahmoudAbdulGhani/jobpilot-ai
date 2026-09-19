import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SuggestionDecision = Literal[True]


class SuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID
    job_id: uuid.UUID | None = None
    job_title: str | None = None
    company: str | None = None
    kind: str
    suggested_due_at: datetime | None
    draft_message: str | None
    reason: str
    state: str
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SuggestionList(BaseModel):
    items: list[SuggestionResponse]
    total: int
    page: int
    page_size: int


class SuggestionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: SuggestionDecision
