"""Small OAuth interface. Deliberately has no mail send, list, read or watch API."""
import base64
import hashlib
import json
from typing import Protocol
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, EmailStr, Field

SCOPES = {"send": "https://www.googleapis.com/auth/gmail.send",
          "read_replies": "https://www.googleapis.com/auth/gmail.readonly"}
IDENTITY_SCOPES = {"openid", "email"}


class MailboxError(Exception):
    def __init__(self, code="provider_unavailable", status=503):
        self.code, self.status = code, status
        super().__init__(code)


class Identity(BaseModel):
    sub: str = Field(min_length=1, max_length=255)
    email: EmailStr = Field(max_length=320)
    email_verified: bool


class Tokens(BaseModel):
    access_token: str = Field(min_length=1, max_length=8192, repr=False)
    refresh_token: str | None = Field(default=None, max_length=8192, repr=False)
    expires_in: int = Field(gt=0, le=86400)
    scope: str = Field(max_length=8192)
    token_type: str


class MailboxProvider(Protocol):
    name: str
    def authorize(self, state: str, verifier: str, capabilities: list[str]) -> str: ...
    def exchange(self, code: str, verifier: str) -> Tokens: ...
    def identity(self, access_token: str) -> Identity: ...
    def refresh(self, refresh_token: str) -> Tokens: ...
    def revoke(self, token: str) -> None: ...


def cipher(settings):
    try:
        return Fernet(settings.JOBPILOT_MAILBOX_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError):
        raise MailboxError("not_configured") from None


def seal(settings, owner, value):
    return cipher(settings).encrypt(json.dumps({"owner":str(owner), "value":value}).encode()).decode()


def unseal(settings, owner, value):
    try:
        payload = json.loads(cipher(settings).decrypt(value.encode()))
        if payload["owner"] != str(owner): raise ValueError()
        return payload["value"]
    except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
        raise MailboxError("credential_unavailable", 409) from None


def validate_configuration(settings):
    cipher(settings)
    for url in (settings.JOBPILOT_GOOGLE_REDIRECT_URI, settings.JOBPILOT_MAILBOX_SETTINGS_URL):
        parsed = urlparse(url)
        local = settings.ENVIRONMENT != "production" and parsed.hostname in ("localhost", "127.0.0.1")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme != "https" and not (local and parsed.scheme == "http")):
            raise MailboxError("not_configured")
    if urlparse(settings.JOBPILOT_GOOGLE_REDIRECT_URI).path != "/api/mailboxes/oauth/callback":
        raise MailboxError("not_configured")


class GoogleMailboxProvider:
    name = "google"
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def authorize(self, state, verifier, capabilities):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id":self.settings.JOBPILOT_GOOGLE_CLIENT_ID, "redirect_uri":self.settings.JOBPILOT_GOOGLE_REDIRECT_URI,
            "response_type":"code", "scope":" ".join(sorted(IDENTITY_SCOPES | {SCOPES[c] for c in capabilities})),
            "state":state, "code_challenge":challenge, "code_challenge_method":"S256",
            "access_type":"offline", "prompt":"consent select_account", "include_granted_scopes":"true"})

    def _request(self, method, url, **kwargs):
        try:
            with httpx.Client(timeout=10, follow_redirects=False, transport=self.transport) as client:
                with client.stream(method, url, **kwargs) as response:
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 65536: raise MailboxError()
                    if url.endswith("/revoke") and response.status_code == 200: return {}
                    body = json.loads(data)
                    if response.status_code != 200:
                        if body.get("error") in ("invalid_grant", "invalid_token"):
                            raise MailboxError("reconnect_required", 409)
                        raise MailboxError()
                    return body
        except (httpx.HTTPError, ValueError, AttributeError):
            raise MailboxError() from None

    def _token(self, **params):
        body = self._request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id":self.settings.JOBPILOT_GOOGLE_CLIENT_ID,
            "client_secret":self.settings.JOBPILOT_GOOGLE_CLIENT_SECRET, **params})
        try:
            token = Tokens.model_validate(body)
            if token.token_type.lower() != "bearer": raise ValueError()
            return token
        except ValueError: raise MailboxError("invalid_provider_response", 502) from None

    def exchange(self, code, verifier):
        return self._token(grant_type="authorization_code", code=code, code_verifier=verifier,
            redirect_uri=self.settings.JOBPILOT_GOOGLE_REDIRECT_URI)

    def identity(self, access_token):
        try:
            identity = Identity.model_validate(self._request("GET", "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": "Bearer " + access_token}))
            if not identity.email_verified: raise ValueError()
            return identity
        except ValueError: raise MailboxError("identity_unverified", 409) from None

    def refresh(self, refresh_token):
        return self._token(grant_type="refresh_token", refresh_token=refresh_token)

    def revoke(self, token):
        self._request("POST", "https://oauth2.googleapis.com/revoke", data={"token":token})


class TestMailboxProvider(GoogleMailboxProvider):
    name = "google-test"
    def authorize(self, state, verifier, capabilities):
        return self.settings.JOBPILOT_GOOGLE_REDIRECT_URI + "?" + urlencode({"state":state,"code":"synthetic"})
    def exchange(self, code, verifier):
        return Tokens(access_token="synthetic-access", refresh_token="synthetic-refresh", expires_in=3600,
            scope=" ".join(IDENTITY_SCOPES | set(SCOPES.values())), token_type="Bearer")
    def identity(self, token):
        return Identity(sub="synthetic-account", email="mailbox@example.com", email_verified=True)
    def refresh(self, token): return self.exchange("synthetic", "synthetic")
    def revoke(self, token): pass


def provider_for(settings) -> MailboxProvider:
    validate_configuration(settings)
    if settings.JOBPILOT_MAILBOX_TEST_PROVIDER:
        if not settings.E2E_TEST_MODE or settings.POSTGRES_DB != settings.POSTGRES_TEST_DB:
            raise MailboxError("test_provider_forbidden")
        return TestMailboxProvider(settings)
    if not settings.JOBPILOT_GOOGLE_CLIENT_ID or not settings.JOBPILOT_GOOGLE_CLIENT_SECRET:
        raise MailboxError("not_configured")
    return GoogleMailboxProvider(settings)
