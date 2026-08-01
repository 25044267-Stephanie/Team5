"""Test-only factories that insert real rows into the MySQL test database.

Replaces the old JSON-era pattern of `monkeypatch.setattr(hotel_app, "bookings", [...])`
— the app now reads/writes MySQL directly, so tests must create real rows
instead of swapping out an in-memory list.
"""

from datetime import datetime

from werkzeug.security import generate_password_hash

from models import Booking, Feedback, LoyaltyPoint, ReservationRequest, Room, User, db


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def make_user(username, password="password123", role="user", points=0, last_seen_tier=None):
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        points=points,
        last_seen_tier=last_seen_tier,
    )
    db.session.add(user)
    db.session.commit()
    return user.to_dict()


def set_points(username, points):
    user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one()
    user.points = points
    db.session.commit()


def make_room(room_number, room_type="Single", price=100, status="Available", image_url=None):
    room = Room(room_number=int(room_number), room_type=room_type, price=price, status=status, image_url=image_url)
    db.session.add(room)
    db.session.commit()
    return room.to_dict()


def make_booking(
    id=None,
    username="user",
    guest_first_name="Alex",
    guest_last_name="Guest",
    guest_name=None,
    phone_number="91234567",
    email="alex@example.com",
    room_id=None,
    room_number=12,
    room_type="Single",
    price=100,
    checkin_date="2026-07-01",
    checkout_date="2026-07-03",
    status="Booked",
    points_redeemed=0,
    points_discount=0,
    total_price=None,
    points_awarded=False,
    points_earned=0,
    points_base=None,
    points_tier=None,
    points_earned_seen=False,
    archived=False,
    created_at=None,
    checked_out_at=None,
):
    booking = Booking(
        id=id,
        username=username,
        guest_first_name=guest_first_name,
        guest_last_name=guest_last_name,
        guest_name=guest_name if guest_name is not None else f"{guest_first_name} {guest_last_name}",
        phone_number=phone_number,
        email=email,
        room_id=room_id,
        room_number=int(room_number),
        room_type=room_type,
        price=price,
        checkin_date=_parse_date(checkin_date),
        checkout_date=_parse_date(checkout_date),
        status=status,
        points_redeemed=points_redeemed,
        points_discount=points_discount,
        total_price=total_price if total_price is not None else price,
        points_awarded=points_awarded,
        points_earned=points_earned,
        points_base=points_base,
        points_tier=points_tier,
        points_earned_seen=points_earned_seen,
        archived=archived,
        created_at=created_at,
        checked_out_at=checked_out_at,
    )
    db.session.add(booking)
    db.session.commit()
    return booking.to_dict()


def make_feedback(
    id=None,
    booking_id=1,
    username="user",
    guest_name="Alex Guest",
    room_number=12,
    room_type="Single",
    checkin_date="2026-07-01",
    checkout_date="2026-07-03",
    facilities_rating=5,
    amenities_rating=4,
    comfort_cleanliness_rating=3,
    additional_feedback="Quiet room and friendly staff.",
    submitted_at=None,
):
    entry = Feedback(
        id=id,
        booking_id=booking_id,
        username=username,
        guest_name=guest_name,
        room_number=int(room_number),
        room_type=room_type,
        checkin_date=_parse_date(checkin_date),
        checkout_date=_parse_date(checkout_date),
        facilities_rating=facilities_rating,
        amenities_rating=amenities_rating,
        comfort_cleanliness_rating=comfort_cleanliness_rating,
        additional_feedback=additional_feedback,
        submitted_at=submitted_at,
    )
    db.session.add(entry)
    db.session.commit()
    return entry.to_dict()


def make_request(
    id=None,
    username="user",
    room_number=12,
    room_type="Single",
    category="Other",
    message="Other request: test",
    guest_name="Alex Guest",
    priority="Low",
    estimated_time="15-30 minutes (non-peak hours)",
    estimated_min=15,
    estimated_max=30,
    queue_ticket=None,
    status="Pending",
    received=False,
    cancelled_by=None,
    created_at=None,
):
    entry = ReservationRequest(
        id=id,
        username=username,
        room_number=int(room_number),
        room_type=room_type,
        category=category,
        message=message,
        guest_name=guest_name,
        priority=priority,
        estimated_time=estimated_time,
        estimated_min=estimated_min,
        estimated_max=estimated_max,
        status=status,
        received=received,
        cancelled_by=cancelled_by,
        created_at=created_at,
    )
    db.session.add(entry)
    db.session.flush()
    entry.queue_ticket = queue_ticket if queue_ticket is not None else f"#{entry.id:03d}"
    db.session.commit()
    return entry.to_dict()


def make_points_adjustment(
    id=None,
    username="user",
    admin_username="admin",
    points=10,
    reason="Compensation",
    is_expiry=False,
    created_at=None,
):
    entry = LoyaltyPoint(
        id=id,
        username=username,
        admin_username=admin_username,
        points=points,
        reason=reason,
        is_expiry=is_expiry,
        created_at=created_at,
    )
    db.session.add(entry)
    db.session.commit()
    return entry.to_dict()
