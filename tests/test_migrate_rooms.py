"""Focused tests for idempotent data.json → MySQL room migration."""

import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

import app as hotel_app
from models import Room, db

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_SCRIPTS))

from migrate_json_to_mysql import DEFAULT_JSON_PATH, Summary, migrate_rooms  # noqa: E402


@pytest.fixture()
def empty_rooms(clean_db):
    """Start from the default clean_db fixture, then clear rooms only."""
    with hotel_app.app.app_context():
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        db.session.execute(text("TRUNCATE TABLE rooms"))
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.session.commit()
        yield


def _load_source():
    path = Path(DEFAULT_JSON_PATH)
    assert path.is_file(), f"Missing verified room source: {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    rooms = data.get("rooms") or []
    assert len(rooms) == 25, f"Expected 25 original rooms in data.json, found {len(rooms)}"
    return data, rooms


def test_data_json_is_verified_room_source():
    data, rooms = _load_source()
    numbers = sorted(int(r["room_number"]) for r in rooms)
    assert numbers[0] == 2
    assert numbers[-1] == 48
    assert all("type" in r and "price" in r and "image" in r for r in rooms)
    bak = Path(os.path.dirname(DEFAULT_JSON_PATH)) / "data.json.bak"
    if bak.is_file():
        bak_rooms = json.loads(bak.read_text(encoding="utf-8")).get("rooms") or []
        assert len(bak_rooms) != 25


def test_migrate_rooms_into_empty_database(empty_rooms):
    data, source_rooms = _load_source()
    summary = Summary("rooms")
    with hotel_app.app.app_context():
        migrate_rooms(data, summary)
        assert summary.migrated == 25
        assert summary.skipped_existing == 0
        assert summary.invalid == 0
        assert Room.query.count() == 25
        stored = {
            (r.id, r.room_number, r.room_type, float(r.price), r.image_url)
            for r in Room.query.all()
        }
        expected = {
            (
                r["id"],
                int(r["room_number"]),
                r["type"],
                float(r["price"]),
                r.get("image"),
            )
            for r in source_rooms
        }
        assert stored == expected


def test_migrate_rooms_twice_is_idempotent(empty_rooms):
    data, _ = _load_source()
    first = Summary("rooms")
    second = Summary("rooms")
    with hotel_app.app.app_context():
        migrate_rooms(data, first)
        migrate_rooms(data, second)
        assert first.migrated == 25
        assert second.migrated == 0
        assert second.skipped_existing == 25
        assert Room.query.count() == 25


def test_migrate_skips_by_room_number_even_if_id_differs(empty_rooms):
    data, source_rooms = _load_source()
    with hotel_app.app.app_context():
        sample = source_rooms[0]
        db.session.add(
            Room(
                id=9999,
                room_number=int(sample["room_number"]),
                room_type=sample["type"],
                price=sample["price"],
                status="Available",
                image_url=sample.get("image"),
            )
        )
        db.session.commit()
        summary = Summary("rooms")
        migrate_rooms(data, summary)
        assert summary.migrated == 24
        assert summary.skipped_existing == 1
        assert Room.query.count() == 25
