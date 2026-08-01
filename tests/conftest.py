"""Pytest fixtures for a MySQL-backed test suite.

Tests run against MYSQL_TEST_DATABASE (see .env.example), never the dev
database. Every test gets a clean database (all tables truncated, then the
two default admin/user accounts reseeded) so tests never depend on
execution order and never leave residue behind for the next test or for a
real dev database.
"""

import os

from dotenv import load_dotenv

load_dotenv()
# Force the app to configure itself against the TEST database, not the dev
# one — this must happen before `app`/`config`/`models` are imported by
# anything (including test_app.py's `import app as hotel_app`), since
# config.py reads MYSQL_DATABASE exactly once at import time.
os.environ["MYSQL_DATABASE"] = os.environ.get("MYSQL_TEST_DATABASE", "hotel_management_test")

import pytest
from werkzeug.security import generate_password_hash

import app as hotel_app
from models import Booking, Feedback, LoyaltyPoint, ReservationRequest, Room, User, db

DEFAULT_ACCOUNTS = (("admin", "admin123", "admin"), ("user", "user123", "user"))


@pytest.fixture(scope="session", autouse=True)
def _app():
    with hotel_app.app.app_context():
        db.create_all()
    yield hotel_app.app


def _truncate_all():
    db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 0"))
    for model in (LoyaltyPoint, ReservationRequest, Feedback, Booking, Room, User):
        db.session.execute(db.text(f"TRUNCATE TABLE {model.__tablename__}"))
    db.session.execute(db.text("SET FOREIGN_KEY_CHECKS = 1"))
    db.session.commit()


def _seed_default_accounts():
    for username, password, role in DEFAULT_ACCOUNTS:
        db.session.add(User(username=username, password_hash=generate_password_hash(password), role=role, points=0))
    db.session.commit()


@pytest.fixture(autouse=True)
def clean_db(_app):
    """Give every test a fresh database (just admin/user) inside an app context."""
    with hotel_app.app.app_context():
        _truncate_all()
        _seed_default_accounts()
        yield
        _truncate_all()


@pytest.fixture()
def client():
    return hotel_app.app.test_client()


def login_as(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
