from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

QaEntity = Literal["jobs", "applications", "reminders", "replies", "interviews", "profile", "packs"]


class QaCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str
    id: str
    field: str
    excerpt: str
    href: str


class QaAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str
    question: str
    matches: list[QaCitation]
    total: int
    limit: int


class ProviderQaOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=2000)
    citations: list[QaCitation] = Field(default_factory=list, max_length=20)
    notes: list[str] = Field(default_factory=list, max_length=10)


class QaAiAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str
    question: str
    source: Literal["ai", "structured"]
    answer: str
    citations: list[QaCitation] = Field(default_factory=list)
    matches: list[QaCitation] = Field(default_factory=list)
    total: int
    limit: int
    provider: str | None = None
    model: str | None = None
    reason: str | None = None