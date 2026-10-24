"""Create (or reset) a city administrator from the command line.

    python -m civicloop.make_admin --email you@example.org --name "Your Name" --city Chandigarh --pincode 160017

An address listed in CIVICLOOP_PLATFORM_ADMINS cannot be claimed through the public sign-up form, so this is how the
first platform administrator is made. The password is read from CIVICLOOP_ADMIN_PASSWORD, or asked for at the prompt,
so it never lands in your shell history.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from civicloop.auth import hash_password
from civicloop.db import create_engine, create_session_factory, init_db
from civicloop.models import User, UserRole
from civicloop.tenancy import get_or_create_tenant, normalise_pincode


def make_admin(session, *, email: str, name: str, password: str, city: str, pincode: str, state: str | None = None) -> User:
    email = email.strip().lower()
    tenant, _ = get_or_create_tenant(session, city, state, verified=True)
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(name=name.strip(), email=email, role=UserRole.ADMIN, password_hash=hash_password(password), tenant_id=tenant.id, pincode=normalise_pincode(pincode))
        session.add(user)
    else:  # an existing account: make it an active admin with the new password, and end its old sign-ins
        user.role, user.is_active, user.password_hash = UserRole.ADMIN, True, hash_password(password)
        user.token_version = (user.token_version or 0) + 1
    session.commit()
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=os.getenv("CIVICLOOP_DATABASE_URL", "sqlite:///civicloop.db"))
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--city", required=True)
    parser.add_argument("--pincode", required=True)
    parser.add_argument("--state")
    args = parser.parse_args()

    password = os.getenv("CIVICLOOP_ADMIN_PASSWORD") or getpass.getpass("Password (12 characters or more): ")
    engine = create_engine(args.database_url)
    if args.database_url.startswith("sqlite"):
        init_db(engine)  # a brand-new development database; in production run `alembic upgrade head` first
    with create_session_factory(engine)() as session:
        user = make_admin(session, email=args.email, name=args.name, password=password, city=args.city, pincode=args.pincode, state=args.state)
        print(f"Administrator ready: {user.email} ({args.city})")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        sys.exit(str(error))
