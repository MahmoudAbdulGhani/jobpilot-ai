from pydantic import BaseModel, ConfigDict, Field


class PlanLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    total: int | None = Field(default=None, ge=0, le=10000)
    profile: int | None = Field(default=None, ge=0, le=10000)
    fit: int | None = Field(default=None, ge=0, le=10000)
    pack: int | None = Field(default=None, ge=0, le=10000)
    interview: int | None = Field(default=None, ge=0, le=10000)
    transcription: int | None = Field(default=None, ge=0, le=10000)
    speech: int | None = Field(default=None, ge=0, le=10000)
    qa: int | None = Field(default=None, ge=0, le=10000)
