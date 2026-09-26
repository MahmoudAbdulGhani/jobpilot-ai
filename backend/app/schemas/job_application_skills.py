import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: uuid.UUID
    requirement_id: str = Field(pattern=r"^req-[0-9]+$", max_length=30)
    confirmed: Literal[True]


class ApplicationSkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    analysis_id: uuid.UUID
    skill: str
    importance: str
    job_quote: str
    created_at: datetime


class ApplicationSkillList(BaseModel):
    items: list[ApplicationSkillResponse]
