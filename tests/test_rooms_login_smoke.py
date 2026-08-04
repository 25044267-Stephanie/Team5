"""Narrow smoke tests for admin login and room booking after MySQL cutover.

Uses MYSQL_TEST_DATABASE only (forced by conftest). Does not touch the
development schema.
"""

from datetime import date, timedelta

from repository import create_booking, create_room, list_rooms
from tests.conftest import login_as


def test_admin_can_login_with_admin123(client):
    response = login_as(client, "admin", "admin123")
    assert response.status_code == 302
    assert "/admin/dashboard" in (response.headers.get("Location") or "")
    with client.session_transaction() as sess:
        assert sess.get("username") == "admin"
        assert sess.get("role") == "admin"


def test_normal_user_can_login(client):
    response = login_as(client, "user", "user123")
    assert response.status_code == 302
    assert "/user/dashboard" in (response.headers.get("Location") or "")


def test_user_sees_available_rooms_with_book_now(client):
    create_room(2, "Available")
    create_room(3, "Booked")
    rooms = {room["room_number"]: room for room in list_rooms()}
    assert rooms["2"]["status"] == "Available"
    assert rooms["3"]["status"] == "Booked"

    login_as(client, "user", "user123")
    response = client.get("/rooms")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Room 2" in html
    assert "Book Now" in html
    # Booked rooms are hidden from non-admin users.
    assert "Room 3" not in html


def test_user_can_open_book_page_and_create_booking(client):
    room = create_room(6, "Available")
    login_as(client, "user", "user123")

    response = client.get(f"/book/{room['id']}")
    assert response.status_code == 200

    checkin = (date.today() + timedelta(days=10)).isoformat()
    checkout = (date.today() + timedelta(days=12)).isoformat()
    response = client.post(
        f"/book/{room['id']}",
        data={
            "guest_first_name": "Test",
            "guest_last_name": "Guest",
            "phone_number": "91234567",
            "email": "test@example.com",
            "checkin_date": checkin,
            "checkout_date": checkout,
            "points_redeemed": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert "/bookings" in (response.headers.get("Location") or "")

    bookings_page = client.get("/bookings")
    assert bookings_page.status_code == 200
    html = bookings_page.get_data(as_text=True)
    assert "Test Guest" in html or "Room 6" in html


def test_overlapping_booking_still_rejected(client):
    room = create_room(9, "Available")
    checkin = (date.today() + timedelta(days=20)).isoformat()
    checkout = (date.today() + timedelta(days=22)).isoformat()
    create_booking(
        room_id=room["id"],
        room_number=room["room_number"],
        room_type=room["type"],
        price=room["price"],
        checkin_date=checkin,
        checkout_date=checkout,
        username="user",
        guest_first_name="A",
        guest_last_name="B",
        phone_number="91234567",
        email="a@example.com",
    )

    login_as(client, "user", "user123")
    response = client.post(
        f"/book/{room['id']}",
        data={
            "guest_first_name": "C",
            "guest_last_name": "D",
            "phone_number": "98765432",
            "email": "c@example.com",
            "checkin_date": checkin,
            "checkout_date": checkout,
            "points_redeemed": "0",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"already booked for the selected dates" in response.data
