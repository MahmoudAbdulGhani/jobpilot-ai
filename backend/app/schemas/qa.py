from typing import Literal

from pydantic import BaseModel, ConfigDict

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
