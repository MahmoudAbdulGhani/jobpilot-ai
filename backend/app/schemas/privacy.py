from typing import Literal

from pydantic import BaseModel, ConfigDict


class MatrixRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    fields_used: list[str]
    used_for: list[str]
    provider: str
    retention: str
    consent_key: str | None
    required: bool
    allowed: bool
    managed_by: str


class PrivacyMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[MatrixRow]


class ConsentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    allowed: bool
    confirm: Literal[True]
