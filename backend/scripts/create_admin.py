"""Create an admin account (use it to seed the first one).

    docker compose run --rm api python -m scripts.create_admin \\
        --email head@lasrra.example --name "Head of Engineering"

The password is read from the ADMIN_PASSWORD environment variable if set, otherwise prompted for
twice. It is never accepted as a command-line argument (it would land in shell history).
"""

import argparse
import getpass
import os
import sys

from pydantic import ValidationError

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.schemas.users import UserCreate
from app.services.users import create_user


def _read_password() -> str:
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Password (10-128 characters): ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="Full name")
    args = parser.parse_args()

    try:
        data = UserCreate(
            full_name=args.name, email=args.email, password=_read_password(), role=UserRole.admin
        )
    except ValidationError as exc:
        sys.exit(
            "Invalid input:\n" + "\n".join(f"  {e['loc'][-1]}: {e['msg']}" for e in exc.errors())
        )

    with SessionLocal() as db:
        try:
            user = create_user(db, data, actor=None)
        except AppError as exc:
            sys.exit(f"{exc.code}: {exc.message}")
    print(f"Created admin {user.email} ({user.id})")


if __name__ == "__main__":
    main()
