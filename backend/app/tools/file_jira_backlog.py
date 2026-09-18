"""Create-only batch runner for jobpilot backlog (JA project).

Reads jira_batch_59.json (59 items: epics then stories), creates each via the
committed create-only scaffold, disabled-by-default gate honored, stops on the
first error, never lists/reads back/updates/deletes. Token from gitignored
.env only. Caller must not run this from a box without outbound network.
"""

import json
from pathlib import Path

from app.core.config import get_settings
from app.services.jira_client import (
    JiraClient,
    JiraDisabledError,
    jira_client_from_settings,
)

BATCH_NAME = "jira_batch_59.json"
BASE = Path(__file__).resolve().parents[3]


def _summary(item: dict) -> str:
    return str(item.get("summary") or item.get("key") or "").strip()


def _description(item: dict) -> str | None:
    d = item.get("description")
    return str(d).strip() if d else None


def main() -> int:
    settings = get_settings()
    if not settings.JIRA_ENABLED:
        print("Jira disabled (JIRA_ENABLED is False); nothing created.")
        return 1
    client = jira_client_from_settings(settings)
    batch_file = BASE / "backend" / BATCH_NAME
    if not batch_file.is_file():
        batch_file = BASE / "backend" / "app" / "tools" / BATCH_NAME
    with open(batch_file, encoding="utf-8") as fh:
        items = json.load(fh)  # type: ignore[arg-type]
    created = 0
    for item in items:
        summary = _summary(item)
        if not summary:
            print("SKIP empty summary; stopping (no silent skip).")
            return 2
        try:
            result = client.create_task(
                summary=summary,
                description=_description(item),
            )
        except JiraDisabledError as exc:
            print(f"STOPPED {exc}")
            return 1
        created += 1
        print(f"CREATED {result.get('key')}: {summary}")
    print(f"TOTAL {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
