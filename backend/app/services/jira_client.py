"""Create-only Jira Cloud client, disabled by default.

This is a deliberately tiny scaffold so opencode can file tasks into a Jira
project. It implements exactly one capability -- create an issue -- and nothing
else: no listing, searching, updating, deleting, or reading back of existing
issues.

Safety model (matches the OAuth-safe e2e pattern elsewhere in this app):
  * Disabled by default: nothing here can run unless ``JIRA_ENABLED`` is set to
    ``True`` in the environment. Every function raises the generic
    "not enabled" marker when disabled, so an ordinary deployment path never
    opens a connection.
  * The API token lives only in the gitignored local ``.env`` as
    ``ATLASSIAN_API_TOKEN`` (the Settings field is ``repr=False`` and is never
    serialized). It is never read from code, never logged, and never echoed by
    this module.

The live reachability/auth smoke test cannot be performed from this box (no
outbound network); the operator runs ``scripts/check_jira.ps1`` on their side.
"""

import base64
import json
from typing import Any

import httpx

from app.core.config import Settings

JIRA_CREATE_ISSUE_PATH = "rest/api/3/issue"
JIRA_CREATE_TIMEOUT_SECONDS = 20.0
# IssueType "Task" is the standard, universally-available Jira Cloud issue
# type name; using a name keeps the scaffold portable across the default
# project scheme.
JIRA_DEFAULT_ISSUE_TYPE = "Task"


class JiraDisabledError(RuntimeError):
    """Raised when a create attempt happens while Jira is disabled.

    A caller should treat this as "feature scaffolding is present but not
    turned on", never as a network failure.
    """


class JiraClient:
    """Create-only Jira Cloud issue client.

    An instance is inert unless constructed with ``enabled=True`` and a
    non-empty API token; otherwise every public method raises
    ``JiraDisabledError`` without touching the network.
    """

    def __init__(self, settings: Settings) -> None:
        self._enabled = bool(settings.JIRA_ENABLED)
        self._token = settings.JIRA_API_TOKEN or ""
        self._user_email = (settings.JIRA_SITE_URL and settings.JIRA_USER_EMAIL) or ""
        self._site_url = (settings.JIRA_SITE_URL or "").rstrip("/")
        self._project_key = (settings.JIRA_PROJECT_KEY or "").strip()
        self._site_url_ok = self._site_url.startswith(("http://", "https://"))

    def create_task(
        self,
        summary: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a single Jira issue with the configured project/type.

        The description is sent as plain text (Jira requires wiki-formatting
        markers or an ADF document body; we deliberately send neither, so the
        description is inert prose, never structural markup).
        """
        if not self._enabled:
            raise JiraDisabledError("Jira integration is disabled (JIRA_ENABLED is False)")
        if not self._site_url_ok or not self._project_key or not self._token:
            raise JiraDisabledError("Jira integration is misconfigured; create disabled")

        url = f"{self._site_url}/{JIRA_CREATE_ISSUE_PATH}"
        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "issuetype": {"name": JIRA_DEFAULT_ISSUE_TYPE},
                "summary": summary,
            }
        }
        if description:
            # Jira Cloud by default renders description as ADF. To stay
            # create-only and inert we send a plain-text description that is
            # unambiguous about its intent; callers that need formatting can
            # build an ADF document themselves later.
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }

        # Atlassian Cloud API tokens authenticate with HTTP Basic using the
        # account email address as the user id, not with a bare bearer token.
        encoded = base64.b64encode(f"{self._user_email}:{self._token}".encode()).decode()
        headers = {"Authorization": f"Basic {encoded}"}

        with httpx.Client(timeout=JIRA_CREATE_TIMEOUT_SECONDS) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    @property
    def enabled(self) -> bool:
        return self._enabled


def jira_client_from_settings(settings: Settings) -> JiraClient:
    return JiraClient(settings)
