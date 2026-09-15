"""Negative survival tests for the create-only Jira scaffold.

These prove the *inert-and-refusing* contract without any network: the
disabled-by-default client must never open a connectionched -- it must raise
``JiraDisabledError`` at the gate (no token/never serially-loaded) the moment
construction or a create attempt happens while ``JIRA_ENABLED`` is unset.

Reachability/auth against the live Atlassian Cloud API cannot be tested from
this box (no outbound network); the operator runs ``scripts/check_jira.ps1``
on their side.
"""

from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

import pytest

from app.services.jira_client import JiraClient, JiraDisabledError


def _settings(**overrides) -> SimpleNamespace:
    defaults = {
        "JIRA_ENABLED": False,
        "JIRA_SITE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "operator@example.com",
        "JIRA_PROJECT_KEY": "JA",
        "JIRA_API_TOKEN": "does-not-matter-when-disabled",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_client_is_inert_and_raises_when_disabled():
    with pytest.raises(JiraDisabledError):
        JiraClient(_settings()).create_task(summary="any")


def test_client_construction_without_enabled_flag_cannot_run():
    client = JiraClient(_settings(JIRA_ENABLED=False))
    assert client.enabled is False
    with pytest.raises(JiraDisabledError):
        client.create_task(summary="blocked")


def test_client_raises_when_missing_token_even_if_enabled():
    # Even with JIRA_ENABLED True, an absent token must keep the create
    # surface disabled -- nothing may open a connection without a credential.
    client = JiraClient(_settings(JIRA_ENABLED=True, JIRA_API_TOKEN=""))
    with pytest.raises(JiraDisabledError):
        client.create_task(summary="no-token")
