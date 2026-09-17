"""Strict interview wire contract: selections and exact evidence, never invented biography."""
import uuid
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Mode = Literal["behavioral", "technical", "mixed"]
Quote = Annotated[str, Field(min_length=1, max_length=300)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InterviewSelection(Strict):
    resume_id: uuid.UUID | None = None
    pack_id: uuid.UUID | None = None
    pack_version: int | None = Field(default=None, ge=1)
    mode: Mode
    question_count: int = Field(ge=2, le=6)

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.resume_id) == bool(self.pack_id) or bool(self.pack_id) != bool(self.pack_version):
            raise ValueError("Choose one reviewed CV or one approved pack version")
        return self


class InterviewStart(InterviewSelection):
    request_key: uuid.UUID
    preview_hash: str = Field(min_length=64, max_length=64)
    confirm: Literal[True]


class AnswerSave(Strict):
    revision: int = Field(ge=0)
    question_number: int = Field(ge=1, le=6)
    answer: str = Field(max_length=3000)


class Advance(Strict):
    request_key: uuid.UUID
    revision: int = Field(ge=0)
    confirm: Literal[True]


class Criterion(Strict):
    assessment: Literal["demonstrated", "needs_detail", "insufficient_evidence"]
    answer_quotes: list[Quote] = Field(max_length=3)
    focus: Literal["connect_to_question", "explain_relevance", "lead_with_point", "separate_steps",
                   "own_contribution", "concrete_outcome", "mechanism", "tradeoffs", "validation"]


class Feedback(Strict):
    relevance: Criterion
    clarity: Criterion
    specificity: Criterion
    technical_knowledge: Criterion


class Question(Strict):
    strategy: Literal["behavioral_example", "technical_approach", "clarify_action", "explain_tradeoff", "measure_result"]
    source: Literal["job", "answer"]
    quote: Quote


class InterviewOutput(Strict):
    question: Question | None
    feedback: Feedback | None
