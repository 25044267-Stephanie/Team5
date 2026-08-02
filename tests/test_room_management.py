"""Focused Room Management tests (admin add/status/delete + seed protection)."""

from datetime import date, timedelta

from repository import (
    create_booking,
    create_room,
    derive_room_details,
    get_seed_room_numbers,
    list_rooms,
)
from tests.conftest import login_as


def _seed_rooms_into_db():
    """Insert all permanent seed rooms from data.json into the disposable test DB."""
    for number in sorted(get_seed_room_numbers()):
        create_room(str(number), "Available")


def test_seed_source_has_exactly_25_unique_numbers():
    seeds = get_seed_room_numbers()
    assert len(seeds) == 25
    assert len(set(seeds)) == 25


def test_derive_mapping_single_double_suite():
    assert derive_room_details("2")["type"] == "Single"
    assert derive_room_details("2")["price"] == 100
    assert derive_room_details("1")["type"] == "Double"
    assert derive_room_details("1")["price"] == 200
    assert derive_room_details("41")["type"] == "Suite"
    assert derive_room_details("41")["price"] == 500


def test_derive_rejects_invalid_numbers():
    assert derive_room_details("abc") is None
    assert derive_room_details("0") is None
    assert derive_room_details("51") is None


def test_admin_can_open_add_room(client):
    login_as(client, "admin", "admin123")
    response = client.get("/admin/rooms/add")
    assert response.status_code == 200
    assert b"Add" in response.data or b"room" in response.data.lower()


def test_user_cannot_open_add_room(client):
    login_as(client, "user", "user123")
    response = client.get("/admin/rooms/add", follow_redirects=False)
    assert response.status_code in (302, 401, 403)


def test_add_room_rejects_duplicate_and_out_of_range(client):
    _seed_rooms_into_db()
    login_as(client, "admin", "admin123")

    bad = client.post("/admin/rooms/add", data={"room_number": "0", "status": "Available"})
    assert bad.status_code == 200
    assert b"1 to 50" in bad.data

    high = client.post("/admin/rooms/add", data={"room_number": "51", "status": "Available"})
    assert high.status_code == 200
    assert b"1 to 50" in high.data

    dup = client.post("/admin/rooms/add", data={"room_number": "2", "status": "Available"})
    assert dup.status_code == 200
    assert b"already exists" in dup.data


def test_add_non_seed_room_increases_total_above_25(client):
    _seed_rooms_into_db()
    # Find a free number in 1-50 not in seeds (seeds use 25 of 50; pick unused).
    seeds = get_seed_room_numbers()
    free = next(n for n in range(1, 51) if n not in seeds)
    login_as(client, "admin", "admin123")
    response = client.post(
        "/admin/rooms/add",
        data={"room_number": str(free), "status": "Available"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    rooms = list_rooms()
    assert len(rooms) == 26
    assert {int(r["room_number"]) for r in rooms} >= seeds


def test_seed_room_delete_rejected(client):
    _seed_rooms_into_db()
    rooms = {int(r["room_number"]): r["id"] for r in list_rooms()}
    seed_number = sorted(get_seed_room_numbers())[0]
    login_as(client, "admin", "admin123")
    response = client.post(f"/admin/rooms/delete/{rooms[seed_number]}")
    assert response.status_code == 409
    assert b"seed" in response.data.lower()
    assert len(list_rooms()) == 25


def test_room_with_booking_history_delete_rejected(client):
    _seed_rooms_into_db()
    seeds = get_seed_room_numbers()
    free = next(n for n in range(1, 51) if n not in seeds)
    room = create_room(str(free), "Available")
    create_booking(
        room_id=room["id"],
        room_number=room["room_number"],
        room_type=room["type"],
        price=room["price"],
        checkin_date=(date.today() + timedelta(days=10)).isoformat(),
        checkout_date=(date.today() + timedelta(days=12)).isoformat(),
        username="user",
        guest_first_name="Test",
        guest_last_name="Guest",
        phone_number="91234567",
        email="guest@example.com",
    )
    login_as(client, "admin", "admin123")
    response = client.post(f"/admin/rooms/delete/{room['id']}")
    assert response.status_code == 409
    assert b"booking" in response.data.lower()


def test_unused_admin_room_can_be_deleted(client):
    _seed_rooms_into_db()
    seeds = get_seed_room_numbers()
    free = next(n for n in range(1, 51) if n not in seeds)
    room = create_room(str(free), "Available")
    login_as(client, "admin", "admin123")
    response = client.post(f"/admin/rooms/delete/{room['id']}")
    assert response.status_code == 200
    assert len(list_rooms()) == 25


def test_status_update_requires_admin(client):
    _seed_rooms_into_db()
    room_id = list_rooms()[0]["id"]
    login_as(client, "user", "user123")
    response = client.post(f"/admin/rooms/status/{room_id}", data={"status": "Maintenance"})
    assert response.status_code == 403


def test_status_available_blocked_when_booked(client):
    _seed_rooms_into_db()
    room = list_rooms()[0]
    create_booking(
        room_id=room["id"],
        room_number=room["room_number"],
        room_type=room["type"],
        price=room["price"],
        checkin_date=(date.today() + timedelta(days=3)).isoformat(),
        checkout_date=(date.today() + timedelta(days=5)).isoformat(),
        username="user",
        guest_first_name="Test",
        guest_last_name="Guest",
        phone_number="91234567",
        email="guest@example.com",
    )
    login_as(client, "admin", "admin123")
    response = client.post(f"/admin/rooms/status/{room['id']}", data={"status": "Available"})
    assert response.status_code == 409


def test_rooms_filter_bar_present_for_admin(client):
    _seed_rooms_into_db()
    login_as(client, "admin", "admin123")
    response = client.get("/rooms")
    assert response.status_code == 200
    assert b"status-filter-bar" in response.data
    assert b"count-Available" in response.data
    assert b"count-Maintenance" in response.data
