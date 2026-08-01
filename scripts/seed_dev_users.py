"""Create the two development demo accounts (admin, user) in MySQL.

Usage (PowerShell, from the project root):
    python scripts\\seed_dev_users.py

Passwords come from SEED_ADMIN_PASSWORD / SEED_USER_PASSWORD in .env (see
.env.example for documented dev defaults) — never hardcoded in application
code. Safe to re-run: existing accounts are left untouched.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from config import Config, ConfigError
from models import User, db

SEED_ACCOUNTS = (
    ("admin", "SEED_ADMIN_PASSWORD", "admin"),
    ("user", "SEED_USER_PASSWORD", "user"),
)


def ensure_seed_accounts():
    """Create admin/user if missing. Must be called inside an app context. Returns (created, skipped)."""
    created, skipped = 0, 0
    for username, password_env, role in SEED_ACCOUNTS:
        password = os.environ.get(password_env)
        if not password:
            print(f"SKIP {username}: {password_env} is not set in the environment.")
            skipped += 1
            continue

        existing = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
        if existing is not None:
            print(f"SKIP {username}: account already exists.")
            skipped += 1
            continue

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

    db.session.commit()
    return created, skipped


def main():
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
                f"Details: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        created, skipped = ensure_seed_accounts()

    print(f"\nSeed summary: {created} account(s) created, {skipped} skipped.")


if __name__ == "__main__":
    main()
