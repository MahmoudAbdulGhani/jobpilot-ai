"""Bounded document contracts; clients never submit evidence or audit fields."""
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_DOCUMENT_CHARS = 30_000
HEADINGS = {"Summary", "Contact", "Experience", "Education", "Skills", "Projects",
            "Languages", "Cover letter", "Curriculum vitae", "Additional information"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimEvidence(StrictModel):
    fact_id: str | None = Field(
        default=None, pattern=r"^fact-[0-9]+$", max_length=30)
    cv_quote: str | None = Field(default=None, min_length=1, max_length=4_000)


class EditableBlock(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    kind: Literal["heading", "paragraph", "bullet"]
    text: str = Field(min_length=1, max_length=2_000)

    @field_validator("text")
    @classmethod
    def plain_text(cls, value: str):
        if not value.strip() or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", value):
            raise ValueError(
                "Use nonempty plain text without control characters")
        return value


class ProviderBlock(EditableBlock):
    evidence: list[ClaimEvidence] = Field(default_factory=list, max_length=10)


class StoredBlock(ProviderBlock):
    origin: Literal["ai", "user"]


class EditableDocument(StrictModel):
    blocks: list[EditableBlock] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounded(self):
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("Block IDs must be unique in a document")
        if sum(len(b.text) for b in self.blocks) > MAX_DOCUMENT_CHARS:
            raise ValueError("Documents are limited to 30,000 characters")
        if not any(b.kind != "heading" for b in self.blocks):
            raise ValueError("A document must contain body text")
        return self


class ProviderDocument(EditableDocument):
    blocks: list[ProviderBlock] = Field(min_length=1, max_length=100)


class StoredDocument(EditableDocument):
    blocks: list[StoredBlock] = Field(min_length=1, max_length=100)


class PackProviderOutput(StrictModel):
    cv: ProviderDocument
    cover_letter: ProviderDocument
    review_notes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("review_notes")
    @classmethod
    def bounded_notes(cls, values):
        if any(not v.strip() or len(v) > 1_000 for v in values):
            raise ValueError(
                "Review notes must be nonempty and at most 1,000 characters")
        return values


class PackGenerate(StrictModel):
    resume_id: uuid.UUID
    idempotency_key: str = Field(
        min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class PackOptions(StrictModel):
    provider: str
    model: str
    available: bool
    reason: str | None = None
    resumes: list[dict[str, str]] = Field(default_factory=list)
    has_profile: bool
    has_description: bool


class PackOperation(StrictModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class PackSave(PackOperation):
    cv: EditableDocument
    cover_letter: EditableDocument


class PackOperations(StrictModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class PackVersionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    number: int
    cv: StoredDocument
    cover_letter: StoredDocument
    created_at: datetime
    approved_at: datetime | None


class PackResponse(StrictModel):
    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID
    status: Literal["generating", "ready", "failed"]
    current_version: int
    version: PackVersionResponse | None
    review_notes: list[str]
    source_snapshot: dict
    is_outdated: bool
    provider: str
    model: str
    outcome_message: str | None
    created_at: datetime


class PackList(StrictModel):
    items: list[PackResponse]
    total: int
    page: int
    page_size: int


class PackVersionList(StrictModel):
    items: list[PackVersionResponse]
    total: int
    page: int
    page_size: int
