"""Create all MySQL tables for the hotel management app.

Usage (PowerShell, from the project root):
    python scripts\\init_db.py            # targets MYSQL_DATABASE from .env
    python scripts\\init_db.py --test      # targets MYSQL_TEST_DATABASE instead

Equivalent to running database/schema.sql by hand, but driven from the
SQLAlchemy models in models.py so it can never drift from what the app
actually expects. Safe to re-run: db.create_all() only creates tables that
don't already exist.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from sqlalchemy.exc import OperationalError

from config import Config, ConfigError, TestConfig
from models import db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test", action="store_true", help="Initialize MYSQL_TEST_DATABASE instead of MYSQL_DATABASE"
    )
    args = parser.parse_args()

    app = Flask(__name__)
    try:
        app.config.from_object(TestConfig if args.test else Config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    db.init_app(app)

    target = "MYSQL_TEST_DATABASE" if args.test else "MYSQL_DATABASE"
    db_name = os.environ.get(target)

    with app.app_context():
        try:
            db.create_all()
        except OperationalError as exc:
            print(
                f"Could not connect to MySQL to initialize '{db_name}'. "
                f"Check that the MySQL server is running and MYSQL_HOST/PORT/USER/"
                f"PASSWORD in .env are correct.\nDetails: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    print(f"Database '{db_name}' is ready — all tables created (or already existed).")


if __name__ == "__main__":
    main()
