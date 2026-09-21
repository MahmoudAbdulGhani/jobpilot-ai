"""Optional speech drafts, isolated from interview answer evaluation."""
import base64
import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from sqlalchemy import func, select
from app.models import InterviewVoiceOperation
from app.services import ai_usage, interview_service
from app.services.account_service import now
from app.services.account_data import active_owner
from app.services.application_pack_service import PackError
from app.services.speech_provider import (OpenAISpeechProvider, SyntheticSpeechProvider,
    SpeechProvider, SpeechFailure, validate_recording, MAX_SPEECH_BYTES)


def configuration(settings):
    test = settings.JOBPILOT_VOICE_TEST_PROVIDER
    if test and not (settings.ENVIRONMENT != "production" and settings.E2E_TEST_MODE
                    and settings.POSTGRES_DB == settings.POSTGRES_TEST_DB):
        raise PackError(503, "Synthetic speech provider requires the guarded test database")
    if not settings.JOBPILOT_VOICE_ENABLED:
        raise PackError(503, "Voice practice is disabled. Text practice remains available.")
    if not test and not settings.JOBPILOT_VOICE_API_KEY:
        raise PackError(503, "Speech provider is not configured. Use text practice.")
    return {"provider": "deterministic-test" if test else settings.JOBPILOT_VOICE_PROVIDER,
        "transcription_model": settings.JOBPILOT_VOICE_TRANSCRIPTION_MODEL,
        "speech_model": settings.JOBPILOT_VOICE_SPEECH_MODEL, "voice": "alloy",
        "max_seconds": settings.JOBPILOT_VOICE_MAX_SECONDS,
        "max_calls_per_session": settings.JOBPILOT_VOICE_MAX_CALLS_PER_SESSION,
        "transcript_minutes": settings.JOBPILOT_VOICE_TRANSCRIPT_MINUTES}


def provider_for(settings) -> SpeechProvider:
    configuration(settings)
    return SyntheticSpeechProvider() if settings.JOBPILOT_VOICE_TEST_PROVIDER else OpenAISpeechProvider(settings)


def public(row):
    status = "unknown" if row.status == "pending" and row.deadline <= now() else row.status
    return {"id": str(row.id), "status": status, "outcome": row.outcome,
        "transcript": row.transcript if row.expires_at > now() else None,
        "usage": row.usage, "audio": None, "media_type": None}


def run(db, owner, session_id, request_key, question_number, consent, kind, settings, audio=b""):
    from app.services.privacy_service import require_consent
    require_consent(db, owner, "ai_voice")
    if consent is not True:
        raise PackError(422, "Explicit external speech-processing consent is required")
    config = configuration(settings)
    active_owner(db, owner)
    session = interview_service.owned(db, owner, session_id, True)
    if kind not in {"transcribe", "speak"}:
        raise PackError(422, "Invalid speech operation")
    if not 1 <= question_number <= len(session.turns):
        raise PackError(409, "Question is unavailable")
    turn = session.turns[question_number-1]
    # Include the displayed excerpt: template questions refer to it. Never
    # accept arbitrary TTS text or silently omit that question context.
    text = turn["text"] + "\nRelevant excerpt: " + turn["question"]["quote"]
    if not 1 <= len(text) <= 600:
        raise PackError(422, "Question exceeds the speech limit")
    duration = 0
    if kind == "transcribe":
        try: duration = validate_recording(audio, settings.JOBPILOT_VOICE_MAX_SECONDS)
        except SpeechFailure: raise PackError(422, "Use a complete 0.25–60 second mono 16 kHz PCM WAV recording") from None
    hashed = hashlib.sha256(str(session_id).encode() + str(question_number).encode() + kind.encode() + (audio if kind == "transcribe" else text.encode())).hexdigest()
    previous = db.scalar(select(InterviewVoiceOperation).where(InterviewVoiceOperation.owner_id == owner,
        InterviewVoiceOperation.request_key == request_key))
    if previous:
        if previous.request_hash != hashed:
            raise PackError(409, "This request key was already used for different content")
        return public(previous)  # Includes failed/unknown outcomes: never redispatch.
    if session.status not in {"ready", "interrupted"} or question_number != len(session.turns):
        raise PackError(409, "Refresh the active question before using voice")
    count = db.scalar(select(func.count()).select_from(InterviewVoiceOperation).where(InterviewVoiceOperation.session_id == session_id))
    if count >= settings.JOBPILOT_VOICE_MAX_CALLS_PER_SESSION:
        raise PackError(429, "Speech request limit reached for this session. Use text practice.")
    timeout = settings.JOBPILOT_VOICE_TIMEOUT_SECONDS
    try:
        token = ai_usage.reserve(db, owner, settings.model_copy(update={"JOBPILOT_AI_TIMEOUT_SECONDS": timeout}), feature="transcription" if kind == "transcribe" else "speech")
    except ai_usage.AIUsageError as error:
        raise PackError(error.status_code, error.message) from None
    row = InterviewVoiceOperation(id=uuid.uuid4(), owner_id=owner, session_id=session_id,
        request_key=request_key, request_hash=hashed, kind=kind, question_number=question_number,
        status="pending", configuration=config, deadline=now()+timedelta(seconds=timeout+5),
        expires_at=now()+timedelta(minutes=settings.JOBPILOT_VOICE_TRANSCRIPT_MINUTES))
    db.add(row); db.commit()  # Claim and quota survive worker interruption.
    op_id = row.id
    try:
        ai_usage.dispatch_guard(db, owner)
        require_consent(db, owner, "ai_voice")
    except Exception:
        row.status, row.outcome = "failed", "consent_or_account_denied"
        ai_usage.release(db, owner, token)
        db.commit()
        raise
    result, failure = None, None
    try:
        provider = provider_for(settings)
        result = ai_usage.bounded_call(lambda: provider.transcribe(audio) if kind == "transcribe" else provider.speak(text), timeout)
        if kind == "transcribe" and (not isinstance(result.transcript, str) or not result.transcript.strip() or len(result.transcript) > 3000):
            raise SpeechFailure("invalid_output")
        if kind == "speak" and (not result.audio or len(result.audio) > MAX_SPEECH_BYTES or result.media_type not in {"audio/mpeg", "audio/wav"}):
            raise SpeechFailure("invalid_output")
    except Exception:
        failure = "speech_failed_or_timed_out"
    finally:
        # No temporary files are created. Late timeout workers can only return
        # data, never write DB state; their bounded HTTP client closes in finally.
        audio = b""
    active_owner(db, owner)
    interview_service.owned(db, owner, session_id, True)  # No resurrecting deleted sessions.
    row = db.get(InterviewVoiceOperation, op_id, populate_existing=True)
    ai_usage.release(db, owner, token)
    if failure or row.deadline < now():
        row.status, row.outcome = "failed", failure or "interrupted"
    else:
        row.status, row.outcome = "succeeded", "draft_only" if kind == "transcribe" else "generated_speech"
        row.transcript = result.transcript if kind == "transcribe" else None
        estimate = Decimal(str(duration))/60*Decimal("0.006") if kind == "transcribe" else Decimal(len(text))*Decimal("0.000015")
        row.usage = {"input_seconds": duration if kind == "transcribe" else None,
            "input_characters": len(text) if kind == "speak" else None,
            "provider_usage": result.usage, "actual_cost_usd": None,
            "estimated_cost_usd": str(estimate.quantize(Decimal("0.000001"), rounding=ROUND_CEILING))}
    db.commit()
    output = public(row)
    if row.status == "succeeded" and kind == "speak":
        output.update(audio=base64.b64encode(result.audio).decode("ascii"), media_type=result.media_type)
    return output
