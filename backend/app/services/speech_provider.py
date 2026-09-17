"""Narrow speech interface. No filesystem, tools, retries, fallback or content logging."""
import io
import struct
import time
import wave
from dataclasses import dataclass
from typing import Protocol
from openai import OpenAI

MAX_SPEECH_BYTES = 1_000_000


class SpeechFailure(Exception):
    pass


@dataclass
class SpeechResult:
    transcript: str | None = None
    audio: bytes | None = None
    media_type: str | None = None
    usage: dict | None = None


class SpeechProvider(Protocol):
    def transcribe(self, audio: bytes) -> SpeechResult: ...
    def speak(self, text: str) -> SpeechResult: ...


def validate_recording(audio: bytes, max_seconds: int) -> float:
    # Deliberately accept only canonical PCM WAV emitted by our recorder. No
    # parsers/codecs/subprocesses interpreting arbitrary uploads or metadata.
    try:
        if len(audio) < 44 or len(audio) > 44 + max_seconds * 32000:
            raise ValueError()
        riff, size, wav, fmt, fmt_size, codec, channels, rate, byte_rate, align, bits, data, count = struct.unpack("<4sI4s4sIHHIIHH4sI", audio[:44])
        if (riff, wav, fmt, fmt_size, codec, channels, rate, byte_rate, align, bits, data) != (b"RIFF", b"WAVE", b"fmt ", 16, 1, 1, 16000, 32000, 2, 16, b"data"):
            raise ValueError()
        if size != len(audio)-8 or count != len(audio)-44 or count % 2 or not 8000 <= count <= max_seconds*32000:
            raise ValueError()
        return count / 32000
    except (ValueError, struct.error):
        raise SpeechFailure("invalid_audio") from None


class OpenAISpeechProvider:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.JOBPILOT_VOICE_API_KEY,
            max_retries=0, timeout=settings.JOBPILOT_VOICE_TIMEOUT_SECONDS)

    def transcribe(self, audio):
        try:
            # Bytes-only multipart upload: neither SDK nor application opens a file.
            response = self.client.audio.transcriptions.create(
                model=self.settings.JOBPILOT_VOICE_TRANSCRIPTION_MODEL,
                file=("recording.wav", audio, "audio/wav"), response_format="json")
            return SpeechResult(transcript=response.text)
        except Exception:
            raise SpeechFailure("provider_unavailable") from None
        finally:
            self.client.close()

    def speak(self, text):
        chunks = bytearray()
        deadline = time.monotonic() + self.settings.JOBPILOT_VOICE_TIMEOUT_SECONDS
        try:
            with self.client.audio.speech.with_streaming_response.create(
                model=self.settings.JOBPILOT_VOICE_SPEECH_MODEL, voice="alloy",
                input=text, response_format="mp3") as response:
                for chunk in response.iter_bytes(chunk_size=8192):
                    if len(chunks)+len(chunk) > MAX_SPEECH_BYTES or time.monotonic() > deadline:
                        raise SpeechFailure("output_limit")
                    chunks.extend(chunk)
            if not chunks:
                raise SpeechFailure("invalid_output")
            return SpeechResult(audio=bytes(chunks), media_type="audio/mpeg")
        except Exception:
            raise SpeechFailure("provider_unavailable") from None
        finally:
            chunks.clear()
            self.client.close()


class SyntheticSpeechProvider:
    def transcribe(self, audio):
        return SpeechResult(transcript="I built a synthetic API and tested its error paths.")

    def speak(self, text):
        with io.BytesIO() as output:
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                wav.writeframes(b"\0\0" * 4000)
            return SpeechResult(audio=output.getvalue(), media_type="audio/wav")
