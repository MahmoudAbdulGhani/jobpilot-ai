"""Bounded lifecycle scheduler. Default is read-only; no content is printed."""
import argparse
import json
from sqlalchemy import select
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AccountDeletion
from app.services.account_data import retention, cleanup_deletion


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true", help="Remove eligible data and process accepted account deletions")
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 20: parser.error("batch-size must be 1–20")
    settings = get_settings()
    with SessionLocal() as db:
        counts = retention(db, settings, dry_run=not args.execute, batch_size=args.batch_size)
        print(json.dumps({"dry_run": not args.execute, "eligible_before": counts}))
        if args.execute:
            # One account per invocation; each file batch and provider attempt is bounded.
            identifier = db.scalar(select(AccountDeletion.id).where(AccountDeletion.status != "complete").order_by(AccountDeletion.updated_at, AccountDeletion.id).limit(1))
            if identifier:
                cleanup_deletion(db, identifier, settings, batch_size=args.batch_size)
                row = db.get(AccountDeletion, identifier)
                print(json.dumps({"cleanup_status": row.status, "failure": row.failure,
                    "provider_revocation_unconfirmed": row.revocation_unconfirmed}))


if __name__ == "__main__":
    try: main()
    except Exception:
        # Database/provider exception strings can contain protected values.
        print(json.dumps({"status":"failed", "reason":"cleanup_unconfirmed; inspect configuration and retry"}))
        raise SystemExit(1) from None
