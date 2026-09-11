import argparse
import getpass
import sys

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jobpilot", description="JobPilot AI management commands"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "setup-owner",
        help="Create the single owner account (interactive, never echoed)",
    )
    args = parser.parse_args(argv)

    if args.command == "setup-owner":
        email, password = prompt_credentials()
        with SessionLocal() as session:
            try:
                user = auth_service.create_first_owner(
                    session, email=email, password=password
                )
            except OwnerAlreadyExistsError:
                print("Refused: an owner account already exists. JobPilot is single-user.")
                return 1
        print(f"Owner account created for {user.email}.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
