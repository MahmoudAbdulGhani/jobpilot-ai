import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InsightLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    href: str


class FitGap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID
    job_title: str
    assessment: str
    requirement: str
    link: InsightLink


class ApplicationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID
    job_title: str
    status: str
    origin: str
    link: InsightLink


class ReplySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply_id: uuid.UUID
    job_id: uuid.UUID | None
    sender_domain: str
    excerpt: str
    link: InsightLink | None


class ReminderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    due_at: datetime | None
    overdue: bool
    link: InsightLink


class InterviewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: uuid.UUID
    job_id: uuid.UUID
    status: str
    link: InsightLink


class InsightsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fit_gaps: list[FitGap]
    fit_counts: dict[str, int]
    applications: list[ApplicationSummary]
    application_counts: dict[str, int]
    replies: list[ReplySummary]
    reply_counts: dict[str, int]
    reminders: list[ReminderSummary]
    reminder_counts: dict[str, int]
    interviews: list[InterviewSummary]
    interview_counts: dict[str, int]
