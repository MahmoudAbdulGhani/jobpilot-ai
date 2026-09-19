import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RankEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_quote: str
    profile_fact: str


class RankReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    evidence: RankEvidence


class RankItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID
    title: str
    company: str
    score: int
    reasons: list[RankReason]
    missing_skills: list[str]
    risks: list[str]
    recommended_action: str


class RankRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_ids: list[uuid.UUID] | None = None
    include_archived: bool = False


class RankRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_count: int | None = None
    top_score: int | None = None
    profile_hash: str
    engine_version: str
    is_stale: bool = False
    items: list[RankItem] | None = None
    created_at: datetime
    updated_at: datetime


class RankRunList(BaseModel):
    items: list[RankRunResponse]
    total: int
    page: int
    page_size: int
