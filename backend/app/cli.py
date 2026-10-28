"""Command line tools for the server operator.

    python -m app.cli create-admin --email you@example.com
    python -m app.cli set-password --email you@example.com
    python -m app.cli seed-admin

The password is asked for interactively, or read from the ADMIN_PASSWORD
environment variable when there is no terminal (for automated setups).
seed-admin runs at every backend start: it creates the account from
ADMIN_EMAIL and ADMIN_PASSWORD (set in .env, never in git) when the database
has none yet, and does nothing otherwise.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import delete, func, select

from app.core.passwords import hash_password, password_problem
from app.db.models import User, UserSession
from app.db.session import session_scope


def _read_password() -> str:
    if env_password := os.environ.get("ADMIN_PASSWORD"):
        return env_password
    if not sys.stdin.isatty():
        raise SystemExit("No terminal: set ADMIN_PASSWORD to pass the password.")
    first = getpass.getpass("New password: ")
    if getpass.getpass("Repeat password: ") != first:
        raise SystemExit("The two passwords are different.")
    return first


def create_admin(email: str) -> int:
    with session_scope() as db:
        if db.scalar(select(func.count()).select_from(User)):
            print("An admin account already exists. Use set-password to change it.")
            return 1
        password = _read_password()
        if problem := password_problem(password):
            print(problem)
            return 1
        db.add(User(email=email.strip().lower(), password_hash=hash_password(password)))
        db.commit()
    print(f"Admin account created for {email}.")
    return 0


def seed_admin() -> int:
    """The admin account from ADMIN_EMAIL / ADMIN_PASSWORD, once. Never stops the start."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        return 0
    with session_scope() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return 0
        if problem := password_problem(password):
            print(f"Admin account not created from ADMIN_PASSWORD: {problem}")
            return 0
        db.add(User(email=email, password_hash=hash_password(password)))
        db.commit()
    print(f"Admin account created for {email} (from ADMIN_EMAIL).")
    return 0


def set_password(email: str) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
        if user is None:
            print(f"No account for {email}.")
            return 1
        password = _read_password()
        if problem := password_problem(password):
            print(problem)
            return 1
        user.password_hash = hash_password(password)
        # A reset may follow a lost or stolen password: sign out everywhere.
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        db.commit()
    print(f"Password changed for {email}. All sessions were signed out.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "set-password"):
        command = commands.add_parser(name)
        command.add_argument("--email", required=True)
    commands.add_parser("seed-admin")
    args = parser.parse_args(argv)
    if args.command == "seed-admin":
        return seed_admin()
    if args.command == "create-admin":
        return create_admin(args.email)
    return set_password(args.email)


if __name__ == "__main__":
    sys.exit(main())
