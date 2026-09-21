import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services import auth_service
from app.services.auth_service import OwnerAlreadyExistsError

MIN_PASSWORD_LENGTH = 12


def prompt_credentials() -> tuple[str, str]:
    email = ""
    while not email or "@" not in email:
        email = input("Owner email: ").strip().lower()
        if not email or "@" not in email:
            print("A valid email address is required.")
    password = getpass.getpass(f"Password (min {MIN_PASSWORD_LENGTH} chars): ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Refused: password must be at least {MIN_PASSWORD_LENGTH} characters.")
        raise SystemExit(1)
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Refused: passwords do not match.")
        raise SystemExit(1)
    return email, password


def prompt_password(label: str = "New password") -> str:
    password = getpass.getpass(f"{label} (min {MIN_PASSWORD_LENGTH} chars): ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Refused: password must be at least {MIN_PASSWORD_LENGTH} characters.")
        raise SystemExit(1)
    confirm = getpass.getpass(f"Confirm {label.lower()}: ")
    if password != confirm:
        print("Refused: passwords do not match.")
        raise SystemExit(1)
    return password


def resolve_local_disposable_database() -> str | None:
    """Return the disposable database URL for local-only resets, or None when
    operating against the normal local database. Must never run in production."""
    import os
    import re
    from sqlalchemy.engine import make_url

    settings = get_settings()
    if settings.ENVIRONMENT == "production":
        print("Refused: reset-password is local-only and cannot run in production.")
        raise SystemExit(1)
    if settings.ENVIRONMENT == "local":
        return None
    raw = os.environ.get("JOBPILOT_DISPOSABLE_DATABASE_URL", "")
    confirm = os.environ.get("JOBPILOT_DISPOSABLE_DATABASE_CONFIRM", "")
    if not raw:
        print("Refused: reset-password outside local mode requires an explicitly confirmed disposable test database (set JOBPILOT_DISPOSABLE_DATABASE_URL and JOBPILOT_DISPOSABLE_DATABASE_CONFIRM).")
        raise SystemExit(1)
    try:
        url = make_url(raw)
    except Exception:
        print("Refused: JOBPILOT_DISPOSABLE_DATABASE_URL is not a valid database URL.")
        raise SystemExit(1) from None
    name = url.database or ""
    protected = {"jobpilot", "jobpilot_test", settings.POSTGRES_DB, settings.POSTGRES_TEST_DB}
    if not (
        url.drivername == "postgresql+psycopg"
        and url.host
        and not url.query
        and name not in protected
        and re.fullmatch(r"jobpilot_disposable_[a-z0-9_]+", name)
        and confirm == name
    ):
        print("Refused: reset-password requires an explicitly confirmed disposable test database (name outside protected databases).")
        raise SystemExit(1)
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jobpilot", description="JobPilot AI management commands"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "setup-owner",
        help="Create the single owner account (interactive, never echoed)",
    )
    recovery = subparsers.add_parser("create-recovery-account", help="Local operator: establish a verified recovery login before deleting the last account")
    recovery.add_argument("--confirm-local-recovery", action="store_true", required=True)
    reset = subparsers.add_parser("reset-password", help="Local-only interactive password reset for one account (never echoed)")
    reset.add_argument("--email", required=True)
    invite = subparsers.add_parser("invite", help="Create one email-bound invitation; local operator only")
    invite.add_argument("--email", required=True)
    invite.add_argument("--hours", type=int, default=24)
    invite.add_argument("--output", required=True, help="New private file for the invitation (never stdout)")
    for name in ("beta-grant", "beta-revoke"):
        beta = subparsers.add_parser(name, help="Authenticated local plan administrator; never enables paid access")
        beta.add_argument("--admin-email", required=True)
        beta.add_argument("--user-id", required=True)
        beta.add_argument("--request-key", required=True, help="UUID for idempotent administration")
        beta.add_argument("--reason", choices=["invited_beta", "evaluation", "support"], required=True)
        if name == "beta-grant": beta.add_argument("--hours", type=int, required=True)
    args = parser.parse_args(argv)

    if args.command in {"beta-grant", "beta-revoke"}:
        import uuid
        from app.core.config import get_settings
        from app.services.entitlements import administer, EntitlementError
        try:
            owner, key = uuid.UUID(args.user_id), uuid.UUID(args.request_key)
            password = getpass.getpass("Administrator password (never echoed): ")
            with SessionLocal() as session:
                result = administer(session, get_settings(), email=args.admin_email, password=password,
                    owner=owner, request_key=key, action="grant" if args.command == "beta-grant" else "revoke",
                    hours=getattr(args, "hours", 0), reason=args.reason)
                print(f"Recorded beta {result.action}; audit {result.id}; grant expiry {result.expires_at}. No payment or paid subscription was created.")
            return 0
        except EntitlementError as error:
            print(error.message); return 1
        except Exception:
            print("Administrative action unavailable; check authentication, bounds and configuration."); return 1

    if args.command == "create-recovery-account":
        from sqlalchemy import select, text
        from app.models import User
        from app.core.security import hash_password
        email, password = prompt_credentials()
        with SessionLocal() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key":auth_service.OWNER_BOOTSTRAP_LOCK_ID})
            if session.scalar(select(User.id).where(User.email == email)):
                print("Refused: use a new recovery-account email.")
                return 1
            session.add(User(email=email, password_hash=hash_password(password), email_verified=True))
            session.commit()
        print("Recovery login created. Verify sign-in before requesting deletion. Web administrator privileges do not exist; local operator access remains required.")
        return 0

    if args.command == "invite":
        import os
        from pydantic import TypeAdapter, EmailStr
        from app.services.account_service import invitation
        from app.core.config import get_settings
        from urllib.parse import urlsplit
        email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()
        if not 1 <= args.hours <= 168:
            parser.error("--hours must be between 1 and 168")
        url = get_settings().JOBPILOT_ACCOUNT_APP_URL.rstrip("/")
        parsed = urlsplit(url)
        if not parsed.netloc or parsed.query or parsed.fragment or parsed.username or (parsed.scheme != "https" and not (get_settings().ENVIRONMENT != "production" and parsed.hostname in {"localhost", "127.0.0.1"} and parsed.scheme == "http")):
            parser.error("Configure a trusted JOBPILOT_ACCOUNT_APP_URL first")
        # O_EXCL prevents clobbering files. On Windows use an operator-private
        # directory with an appropriate ACL; POSIX receives mode 0600.
        with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
            with SessionLocal() as session:
                raw = invitation(session, email, args.hours)
            output.write(f"{url}/register#token={raw}\n")
        print("Invitation written to the selected private file. Share securely; do not log it.")
        return 0

    if args.command == "setup-owner":
        email, password = prompt_credentials()
        with SessionLocal() as session:
            try:
                user = auth_service.create_first_owner(
                    session, email=email, password=password
                )
            except OwnerAlreadyExistsError:
                print("Refused: an owner account already exists.")
                return 1
        print(f"Owner account created for {user.email}.")
        return 0

    if args.command == "reset-password":
        target = resolve_local_disposable_database()
        password = prompt_password()
        if target is not None:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            reset_session = sessionmaker(bind=create_engine(target, hide_parameters=True))
        else:
            reset_session = SessionLocal
        with reset_session() as session:
            user = auth_service.reset_password(session, email=args.email, password=password)
            if user is None:
                print("Refused: no active account found for that email. Nothing was changed.")
                return 1
            reset_email = user.email
        print(f"Password reset complete for {reset_email}. Existing sessions were invalidated.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
