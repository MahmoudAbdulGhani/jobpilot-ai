"""Bounded read-only Gmail adapter. No send, full body or attachment endpoint."""
import json
import re
from email.parser import BytesParser
from email import policy
from typing import Protocol

import httpx

from app.services.mailbox_provider import provider_for

HEADERS = ["Message-ID", "In-Reply-To", "References", "From", "To", "Subject", "Date"]
MESSAGE_FIELDS = "id,threadId,labelIds,internalDate,snippet,payload(headers)"


class SyncError(Exception):
    def __init__(self, code, retry_seconds=60):
        self.code, self.retry_seconds = code, retry_seconds
        super().__init__(code)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,255}", value):
        raise SyncError("invalid_provider_response")
    return value


class ReplyProvider(Protocol):
    def checkpoint(self) -> str: ...
    def message(self, message_id: str) -> dict: ...
    def thread(self, thread_id: str) -> dict: ...
    def history(self, start: str, page: str | None) -> dict: ...
    def find_sent(self, rfc_id: str) -> dict: ...


class GmailReplies:
    def __init__(self, token, transport=None):
        self.token, self.transport, self.calls = token, transport, 0

    def get(self, path, params):
        if self.calls >= 8:
            raise SyncError("batch_limit")
        self.calls += 1
        try:
            with httpx.Client(timeout=5, follow_redirects=False, transport=self.transport) as client:
                with client.stream("GET", "https://gmail.googleapis.com/gmail/v1/users/me/" + path,
                        headers={"Authorization": "Bearer " + self.token}, params=params) as response:
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 262144:
                            raise SyncError("response_limit")
                    if response.status_code == 404:
                        raise SyncError("history_expired" if path == "history" else "message_unavailable")
                    if response.status_code == 400 and path == "history":
                        raise SyncError("page_expired")
                    body = json.loads(data)
                    if response.status_code in (403, 429):
                        reasons = {e.get("reason") for e in body.get("error", {}).get("errors", []) if isinstance(e, dict)}
                        if response.status_code == 429 or reasons & {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"}:
                            delay = response.headers.get("retry-after", "60")
                            raise SyncError("rate_limited", min(3600, max(60, int(delay))) if delay.isdigit() else 60)
                        raise SyncError("reading_permission_required")
                    if response.status_code == 401:
                        raise SyncError("credential_revoked")
                    if response.status_code != 200:
                        raise SyncError("provider_unavailable")
                    if not isinstance(body, dict):
                        raise SyncError("invalid_provider_response")
                    return body
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise SyncError("provider_unavailable") from None

    def message(self, message_id):
        # Partial response explicitly excludes payload bodies/parts and raw MIME.
        return self.get("messages/" + identifier(message_id), {"format": "full", "fields": MESSAGE_FIELDS})

    def checkpoint(self):
        return identifier(self.get("profile", {"fields": "historyId"})["historyId"])

    def thread(self, thread_id):
        return self.get("threads/" + identifier(thread_id), {"format": "metadata", "metadataHeaders": HEADERS,
            "fields": "id,historyId,messages(id,threadId,labelIds)"})

    def history(self, start, page):
        params = {"startHistoryId": identifier(start), "maxResults": 10, "historyTypes": "messageAdded",
            "fields": "historyId,nextPageToken,history(messagesAdded(message(id,threadId)))"}
        if page:
            params["pageToken"] = page
        return self.get("history", params)

    def find_sent(self, rfc_id):
        # Only the server-generated UUID Message-ID can enter this search.
        if not re.fullmatch(r"<[a-f0-9-]{36}@jobpilot\.invalid>", rfc_id):
            raise SyncError("original_identifier_unavailable")
        return self.get("messages", {"q": "in:sent rfc822msgid:" + rfc_id,
            "maxResults": 2, "fields": "messages(id,threadId),nextPageToken"})


class SyntheticReplies:
    """Only constructed behind the existing E2E/test-database provider guard."""
    def __init__(self, attempt):
        self.attempt = attempt
        self.original = BytesParser(policy=policy.default).parsebytes(attempt.raw_message)

    def message(self, message_id):
        original = message_id == self.attempt.provider_message_id
        names = {h: str(self.original.get(h, "")) for h in HEADERS} if original else {
            "Message-ID": f"<{message_id}@example.com>", "From": "Recruiter <recruiter@example.com>",
            "Subject": "Re: synthetic application", "In-Reply-To": str(self.original["Message-ID"]) if message_id == "synthetic-reply" else ""}
        return {"id": message_id, "threadId": self.attempt.provider_thread_id, "labelIds": ["SENT"] if original else ["INBOX"],
            "internalDate": str(int((self.attempt.dispatch_at or self.attempt.created_at).timestamp() * 1000) + (0 if original else 1000)),
            "snippet": "Synthetic reply preview. Thank you for your application.",
            "payload": {"headers": [{"name": k, "value": v} for k, v in names.items()]}}

    def thread(self, thread_id):
        return {"id": thread_id, "historyId": "100", "messages": [{"id": m, "threadId": thread_id}
            for m in (self.attempt.provider_message_id, "synthetic-reply", "synthetic-uncertain")]}

    def history(self, start, page):
        return {"historyId": "101", "history": []}

    def checkpoint(self):
        return "100"

    def find_sent(self, rfc_id):
        return {"messages": []}  # Never turn a simulated send into real acceptance.


def replies_for(settings, token, attempt):
    provider = provider_for(settings)
    return SyntheticReplies(attempt) if provider.name == "google-test" else GmailReplies(token)
