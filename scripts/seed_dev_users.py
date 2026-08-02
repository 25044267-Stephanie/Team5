"""Create/repair development demo accounts (admin, user, steph) in MySQL.

Usage (PowerShell, from the project root):
    python scripts\\seed_dev_users.py
    python scripts\\seed_dev_users.py --ensure-demo-users

Passwords come from SEED_ADMIN_PASSWORD / SEED_USER_PASSWORD /
SEED_STEPH_PASSWORD in .env (see .env.example) — never hardcoded in
application code. Safe to re-run: no duplicate usernames; existing unrelated
users are never deleted. If an account exists, role/password_hash are
repaired only when they no longer match the SEED_* values.

--ensure-demo-users: only admin + steph (no room/booking/feedback changes;
never touches unrelated users). Prefer this on EC2 after --rooms-only migrate.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from sqlalchemy.exc import OperationalError
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config, ConfigError
from models import User, db

SEED_ACCOUNTS = (
    ("admin", "SEED_ADMIN_PASSWORD", "admin"),
    ("user", "SEED_USER_PASSWORD", "user"),
    ("steph", "SEED_STEPH_PASSWORD", "user"),
)

DEMO_ACCOUNTS = (
    ("admin", "SEED_ADMIN_PASSWORD", "admin"),
    ("steph", "SEED_STEPH_PASSWORD", "user"),
)


def ensure_seed_accounts(accounts=SEED_ACCOUNTS):
    """Create or repair the given demo accounts. Must run inside an app context.

    Returns (created, updated, skipped). Existing unrelated users are never deleted.
    If an account already exists, only role / password_hash are corrected when they
    no longer match SEED_* from the environment. Never prints password values.
    """
    created, updated, skipped = 0, 0, 0
    for username, password_env, role in accounts:
        password = os.environ.get(password_env)
        if not password:
            print(f"SKIP {username}: {password_env} is not set in the environment.")
            skipped += 1
            continue

        existing = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
        if existing is None:
            db.session.add(
                User(
                    username=username,
                    password_hash=generate_password_hash(password),
                    role=role,
                    points=0,
                )
            )
            created += 1
            print(f"CREATED {username} (role={role})")
            continue

        changed = False
        if existing.role != role:
            existing.role = role
            changed = True
        if not check_password_hash(existing.password_hash, password):
            existing.password_hash = generate_password_hash(password)
            changed = True

        if changed:
            updated += 1
            print(f"UPDATED {username} (role={role}, password_hash refreshed from {password_env})")
        else:
            skipped += 1
            print(f"SKIP {username}: already matches seed role and password.")

    db.session.commit()
    return created, updated, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ensure-demo-users",
        action="store_true",
        help="Create/repair only admin and steph from SEED_ADMIN_PASSWORD / SEED_STEPH_PASSWORD.",
    )
    args = parser.parse_args(argv)
    accounts = DEMO_ACCOUNTS if args.ensure_demo_users else SEED_ACCOUNTS

    try:
        app = Flask(__name__)
        app.config.from_object(Config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    db.init_app(app)

    with app.app_context():
        try:
            db.session.execute(db.select(User).limit(1))
        except OperationalError as exc:
            print(
                "Could not connect to MySQL. Check that the MySQL server is running "
                "and MYSQL_HOST/PORT/USER/PASSWORD/DATABASE in .env are correct, and "
                "that scripts\\init_db.py has been run.\n"
                f"Details: {type(exc).__name__}",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            created, updated, skipped = ensure_seed_accounts(accounts)
        except Exception:
            db.session.rollback()
            raise

    mode = "demo (admin/steph)" if args.ensure_demo_users else "all seed accounts"
    print(
        f"\nSeed summary ({mode}): {created} created, {updated} updated, {skipped} skipped."
    )


if __name__ == "__main__":
    main()
