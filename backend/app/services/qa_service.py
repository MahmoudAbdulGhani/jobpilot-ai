"""Read-only customer Q&A over the owner's own data.

Keyword search across an explicit field allowlist per entity. GET only, SELECT
only: answering never writes, sends, changes status or deletes anything. Every
match carries a citation (entity, id, field, excerpt, link). An optional
bounded AI layer answers natural-language questions using only the retrieved
excerpts; live provider calls require the ``ai_qa`` consent toggle.
"""
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (ApplicationPack, ApplicationRecord, CandidateProfile,
                        InterviewSession, MailboxReply, SavedJob)
from app.schemas.qa import ProviderQaOutput, QaAiAnswer, QaCitation
from app.services import ai_usage
from app.services.ai_provider import DeterministicTestProvider, GroqResponsesProvider, OpenAIResponsesProvider, ProviderFailure
from app.services import privacy_service
from app.services.profile_suggestion_service import SuggestionError, provider_configuration as profile_provider_configuration

WORD = re.compile(r"[a-z0-9][a-z0-9+#.-]*")
STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have",
    "has", "from", "that", "this", "who", "can", "all", "any", "what", "when",
    "where", "which", "show", "list", "find", "about", "does", "did", "are",
    "was", "were", "have", "has", "had", "there", "their", "they", "them",
}
MAX_LIMIT = 20
MAX_CITATIONS_TO_PROVIDER = 10


def keywords(question: str) -> list[str]:
    tokens = [token.strip(".,:;()\"'") for token in WORD.findall(question.casefold())]
    terms = [token for token in tokens if len(token) >= 3 and token not in STOPWORDS]
    if not terms:
        raise HTTPException(422, "Ask with at least one searchable word")
    return terms


def _excerpt(text: str | None, limit: int = 200) -> str:
    return " ".join((text or "").split())[:limit]


def _field_excerpt(value: object, needle: str) -> str:
    text = value if isinstance(value, str) else str(value)
    lowered = text.casefold()
    position = lowered.find(needle)
    if position < 0:
        return _excerpt(text)
    start = max(0, position - 60)
    return _excerpt(text[start:start + 200])


def _match(text: str, terms: list[str]) -> bool:
    lowered = text.casefold()
    return all(term in lowered for term in terms)


def _rows(db: Session, owner_id: uuid.UUID, entity: str) -> list[tuple[str, str, dict[str, object], str]]:
    """Return (row id, link, allowlisted field map, job context) per entity."""
    if entity == "jobs":
        return [(str(job.id), f"/jobs/{job.id}",
                 {"title": job.title, "company": job.company, "location": job.location or "",
                  "description": job.description or "", "notes": job.notes or ""}, "")
                for job in db.scalars(select(SavedJob).where(SavedJob.owner_id == owner_id))]
    if entity == "applications":
        out = []
        for record in db.scalars(select(ApplicationRecord).where(ApplicationRecord.owner_id == owner_id)):
            out.append((str(record.id), f"/jobs/{record.job_id}",
                        {"status": record.status, "method": record.method, "notes": record.notes or ""}, ""))
        return out
    if entity == "reminders":
        out = []
        for record in db.scalars(select(ApplicationRecord).where(
                ApplicationRecord.owner_id == owner_id, ApplicationRecord.follow_up_date.is_not(None))):
            out.append((str(record.id), "/reminders",
                        {"status": record.status, "reminder_status": record.reminder_status or ""}, ""))
        return out
    if entity == "replies":
        out = []
        for reply in db.scalars(select(MailboxReply).where(MailboxReply.owner_id == owner_id)):
            target = reply.job_id or reply.suggested_job_id
            out.append((str(reply.id), f"/jobs/{target}" if target else "/reminders",
                        {"subject": reply.subject or "", "preview": reply.preview or ""}, ""))
        return out
    if entity == "interviews":
        return [(str(session.id), f"/interviews/{session.id}",
                 {"status": session.status, "mode": session.mode}, "")
                for session in db.scalars(select(InterviewSession).where(
                    InterviewSession.owner_id == owner_id))]
    if entity == "profile":
        profile = db.scalar(select(CandidateProfile).where(CandidateProfile.owner_id == owner_id))
        if profile is None:
            return []
        fields: dict[str, object] = {"headline": profile.headline or "", "location": profile.location or "",
                                     "remote_preference": profile.remote_preference or ""}
        for name in ("skills", "experience", "education", "languages"):
            values = getattr(profile, name) or []
            fields[name] = " | ".join(item if isinstance(item, str) else str(item) for item in values)
        return [(str(profile.id), "/profile", fields, "")]
    if entity == "packs":
        out = []
        for pack in db.scalars(select(ApplicationPack).where(ApplicationPack.owner_id == owner_id)):
            out.append((str(pack.id), f"/jobs/{pack.job_id}",
                        {"status": pack.status,
                         "review_notes": " | ".join(str(note) for note in (pack.review_notes or []))}, ""))
        return out
    raise HTTPException(422, "Unsupported question scope")


def ask(db: Session, owner_id: uuid.UUID, entity: str, question: str, limit: int) -> dict:
    if limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(422, f"Limit must stay within 1 and {MAX_LIMIT}")
    terms = keywords(question)
    matches: list[dict] = []
    total = 0
    for row_id, href, fields, _ in _rows(db, owner_id, entity):
        hits = [(field, value) for field, value in fields.items()
                if _match(str(value), terms)]
        if not hits:
            continue
        total += 1
        if len(matches) >= limit:
            continue
        field, value = hits[0]
        matches.append({"entity": entity, "id": row_id, "field": field,
                        "excerpt": _field_excerpt(value, terms[0]), "href": href})
    return {"entity": entity, "question": question[:500], "matches": matches,
            "total": total, "limit": limit}


def _provider_for(settings: Settings):
    name, model, key = profile_provider_configuration(settings)
    if name == "deterministic-test":
        return DeterministicTestProvider()
    provider_class = GroqResponsesProvider if name == "groq" else OpenAIResponsesProvider
    return provider_class(
        api_key=key,
        model=model,
        timeout=settings.JOBPILOT_AI_TIMEOUT_SECONDS,
        max_output_tokens=settings.JOBPILOT_AI_MAX_OUTPUT_TOKENS,
    )


def _structured_answer(entity: str, matches: list[dict], total: int, limit: int, reason: str) -> QaAiAnswer:
    if not matches:
        answer = f"No matching {entity} fields were found in your saved data."
    else:
        answer = (f"Your saved data contains {total} matching {entity} "
                  f"field(s); showing up to {limit}. The matches below are verbatim "
                  f"excerpts; the search is keyword-based.")
    return QaAiAnswer(entity=entity, question="", source="structured", answer=answer,
                      citations=[QaCitation.model_validate(m) for m in matches], matches=[QaCitation.model_validate(m) for m in matches],
                      total=total, limit=limit, provider=None, model=None, reason=reason)


def answer(db: Session, owner_id: uuid.UUID, entity: str, question: str, limit: int, settings: Settings) -> QaAiAnswer:
    """AI-gated natural-language answer with an always-safe structured fallback."""
    retrieved = ask(db, owner_id, entity, question, limit)
    matches: list[QaCitation] = [QaCitation.model_validate(item) for item in retrieved["matches"]]
    total, question_text = retrieved["total"], retrieved["question"]
    if not settings.JOBPILOT_AI_ENABLED or settings.ENVIRONMENT == "production":
        fallback = _structured_answer(entity, retrieved["matches"], total, limit, "AI features are disabled in this environment.")
        fallback.question = question_text
        return fallback
    if not privacy_service.is_consented(db, owner_id, "ai_qa"):
        fallback = _structured_answer(entity, retrieved["matches"], total, limit, "Consent for AI answers is not granted; showing the structured search.")
        fallback.question = question_text
        return fallback

    sendable = [m.model_dump(mode="json") for m in matches[:MAX_CITATIONS_TO_PROVIDER]]
    try:
        provider = _provider_for(settings)
    except SuggestionError as error:
        fallback = _structured_answer(entity, retrieved["matches"], total, limit, f"AI provider unavailable: {error.message}")
        fallback.question = question_text
        return fallback

    token = None
    try:
        token = ai_usage.reserve(db, owner_id, settings, feature="qa")
        output = provider.answer(question_text, sendable)
        allowed = {tuple(m.model_dump(mode="json").values()) for m in matches[:MAX_CITATIONS_TO_PROVIDER]}
        citations: list[QaCitation] = []
        for citation in output.citations:
            if tuple(citation.model_dump(mode="json").values()) not in allowed:
                raise ProviderFailure("The AI provider cited fields outside the retrieved allowlist.")
            citations.append(citation)
        return QaAiAnswer(entity=entity, question=question_text, source="ai",
                          answer=output.answer, citations=citations,
                          matches=[QaCitation.model_validate(m) for m in matches],
                          total=total, limit=limit, provider=provider.name,
                          model=provider.model, reason=None)
    except ProviderFailure as error:
        fallback = _structured_answer(entity, retrieved["matches"], total, limit, f"AI provider unavailable: {error}. Showing the structured search.")
        fallback.question = question_text
        return fallback
    except ai_usage.AIUsageError as error:
        raise HTTPException(error.status_code, detail=error.message) from error
    finally:
        if token:
            ai_usage.release(db, owner_id, token)
