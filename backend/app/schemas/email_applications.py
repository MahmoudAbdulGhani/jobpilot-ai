import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class EmailReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mailbox_id: uuid.UUID
    pack_id: uuid.UUID
    pack_version: int = Field(ge=1)
    recipient: EmailStr = Field(max_length=254)
    confirm_recipient: EmailStr = Field(max_length=254)
    recipient_source: str = Field(min_length=3, max_length=1000)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("recipient", "confirm_recipient", "subject", mode="before")
    @classmethod
    def safe_header(cls, value):
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Email headers cannot contain control characters")
        if not value.strip():
            raise ValueError("A nonempty value is required")
        return value

    @field_validator("recipient", "confirm_recipient")
    @classmethod
    def ascii_address(cls, value):
        if not value.isascii():
            raise ValueError("Use an ASCII recruitment email address")
        return value

    @field_validator("body", "recipient_source")
    @classmethod
    def text_required(cls, value):
        if not value.strip() or any(ord(c) < 32 and c not in "\r\n\t" for c in value):
            raise ValueError("Enter nonempty text without unsafe control characters")
        return value

    @model_validator(mode="after")
    def addresses_match(self):
        if self.recipient != self.confirm_recipient:
            raise ValueError("Confirm the same recruitment email address")
        return self


class EmailApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: Literal[True]
