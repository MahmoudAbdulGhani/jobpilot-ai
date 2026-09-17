"""Offline only: a bounded synthetic speech smoke plan, never dispatches requests."""
import json
from decimal import Decimal, ROUND_CEILING

QUESTION = "Describe how you tested a synthetic API and handled one failure case."


def build_plan():
    transcription = Decimal(10) / 60 * Decimal("0.006")
    speech = Decimal(len(QUESTION)) * Decimal("0.000015")
    return {
        "live_requests_sent": 0, "planned_live_requests": 2,
        "transcription": {"provider": "openai", "model": "whisper-1",
            "endpoint": "/v1/audio/transcriptions", "seconds": 10,
            "format": "mono 16kHz signed 16-bit PCM WAV", "bytes": 320044,
            "estimated_cost_usd": str(transcription.quantize(Decimal("0.000001"), rounding=ROUND_CEILING))},
        "speech": {"provider": "openai", "model": "tts-1", "voice": "alloy",
            "endpoint": "/v1/audio/speech", "text": QUESTION,
            "input_characters": len(QUESTION), "max_response_bytes": 1000000,
            "estimated_cost_usd": str(speech)},
        "estimated_budget_usd": str((transcription + speech).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)),
        "actual_usage": None, "actual_billing_usd": None,
        "max_retries": 0, "fallback": False,
        "approval_required": "Separate authorization before either live request; this module cannot send requests",
        "acceptance": ["Transcript captures only the synthetic recording; review/edit before submission",
            "No answer/revision advancement on transcription", "Speech audibly matches visible question",
            "Replay uses the same dispatch receipt and sends no new request",
            "No audio files or stored audio; safe failure categories only"],
    }


if __name__ == "__main__":
    print(json.dumps(build_plan(), indent=2))
