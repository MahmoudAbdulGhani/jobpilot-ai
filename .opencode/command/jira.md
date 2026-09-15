---
description: "File a single create-only issue into the Jira project (JA) using the scaffolded app.services.jira_client — requires JIRA_ENABLED in the gitignored .env and does nothing else (no listing/search/update/delete). Use only when the operator has run the reachability+auth smoke (200) on their side."
---

Create exactly ONE Jira Cloud issue in project key **JA** using the existing
create-only scaffold at `backend/app/services/jira_client.py`. This command is
inert unless Jira is actually enabled in the environment — that is the whole
point of the disabled-by-default safety gate.

## Rules (hard)

1. **Create-only.** Call `JiraClient.create_task(summary=..., description=...)`
   over `app.core.config.get_settings()` via `jira_client_from_settings`.
   Do NOT list, search, read back, update, close, or delete anything, and do
   not touch any other Jira REST resource.
2. **Respect the gate.** If construction or the call raises
   `JiraDisabledError` (or `settings.JIRA_ENABLED` is not truthy, or the token
   is empty), STOP and report the exact reason. Never "helpfully" bypass the
   gate, never invent a token, never open a connection while disabled.
3. **Secrets stay out.** The token is read only from the gitignored local
   `.env` through `Settings` (`JIRA_API_TOKEN`, `repr=False`). Never echo,
   log, commit, or inline the token value; never write it to any tracked file.
4. **Description is plain text.** Pass `description` as inert prose only (the
   scaffold sends it as an unformatted string — no wiki/ADF markup). No
   HTML/markup in the summary or description.

## Task content

- `summary` — the task title, derived from the caller's request (fall back to
  the filename or a clear short phrase if none is explicit).
- `description` — a plain-text, unambiguous description of what opencode is
  being asked to do on this Jira item alert.

When the scaffold raises `JiraDisabledError`, reply with exactly:
"Jira is disabled (JIRA_ENABLED is False in .env) — nothing was created. Run
the reachability smoke first, then set JIRA_ENABLED=True and retry."
