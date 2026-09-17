"""Send-only interface: no inbox access and no retries, including ambiguous errors."""
import base64
import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.services.mailbox_provider import MailboxError, provider_for


@dataclass(frozen=True)
class SendResult:
    status: str
    code: str
    http_status: int | None = None
    message_id: str | None = None
    thread_id: str | None = None


class EmailSender(Protocol):
    def send(self, access_token: str, raw: bytes) -> SendResult: ...


class GmailSender:
    def __init__(self, transport=None):
        self.transport = transport

    def send(self, access_token, raw):
        http_status = None
        try:
            with httpx.Client(timeout=20, follow_redirects=False, transport=self.transport) as client:
                with client.stream("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                        headers={"Authorization": "Bearer " + access_token},
                        json={"raw": base64.urlsafe_b64encode(raw).decode("ascii")}) as response:
                    http_status = response.status_code
                    # Definite provider rejection; never repeat automatically.
                    if http_status in (400, 401, 403, 404, 413, 429):
                        return SendResult("failed", "gmail_rejected", http_status)
                    if http_status != 200:
                        return SendResult("unknown", "unconfirmed_provider_result", http_status)
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 65536:
                            return SendResult("unknown", "invalid_provider_response", http_status)
                    body = json.loads(data)
                    message_id, thread_id = body.get("id"), body.get("threadId")
                    if not isinstance(message_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,255}", message_id):
                        return SendResult("unknown", "missing_message_id", http_status)
                    if not isinstance(thread_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,255}", thread_id):
                        thread_id = None
                    return SendResult("sent", "gmail_accepted", http_status, message_id, thread_id)
        except (httpx.HTTPError, ValueError, AttributeError):
            return SendResult("unknown", "transport_or_response_uncertain", http_status)


class SyntheticSender:
    def send(self, access_token, raw):
        return SendResult("simulated", "synthetic_acceptance_no_email", 200, "synthetic-message", "synthetic-thread")


def sender_for(settings):
    provider = provider_for(settings)  # Reuse the guarded provider selection; no fallback.
    if provider.name == "google-test":
        return SyntheticSender()
    if provider.name != "google":
        raise MailboxError("provider_mismatch", 409)
    return GmailSender()
