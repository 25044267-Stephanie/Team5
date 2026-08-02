"""MySQL-backed data-access layer for the hotel management app.

Every function here does a real database operation (query, insert, update,
delete) via the SQLAlchemy models in models.py, returning plain dicts
(model.to_dict()) so the rest of app.py — which is full of pure functions
that only ever consumed plain dicts — keeps working unchanged.

Multi-step operations (booking creation + room status sync, check-in/out,
cancellation, points award/adjust) are wrapped in a single commit with a
rollback on failure, so a partial write can never happen.
"""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from models import Booking, Feedback, LoyaltyPoint, ReservationRequest, Room, User, db

DATA_JSON_PATH = Path(__file__).resolve().parent / "data.json"

SINGAPORE_TZ = ZoneInfo("Asia/Singapore")

ALLOWED_ROOM_TYPES = ("Single", "Double", "Suite")
ALLOWED_ROOM_STATUSES = ("Available", "Booked", "Maintenance")
ARCHIVABLE_BOOKING_STATUSES = {"Checked Out", "Cancelled", "No-Show"}

ROOM_IMAGE_POOLS = {
    "Single": (
        "/static/images/rooms/single-room-1.png",
        "/static/images/rooms/single-room-2.png",
    ),
    "Double": (
        "/static/images/rooms/double-room-1.png",
        "/static/images/rooms/double-room-2.png",
    ),
    "Suite": (
        "/static/images/rooms/suite-room-1.png",
        "/static/images/rooms/suite-room-2.png",
    ),
}

LOYALTY_POINTS_PER_NIGHT = {"Single": 10, "Double": 20, "Suite": 50}
LOYALTY_POINTS_PER_DOLLAR = 10
MINIMUM_POINTS_REDEMPTION = 100
POINTS_EXPIRY_DAYS = 365

LOYALTY_TIERS = [
    ("Bronze", 0, "\U0001f949"),
    ("Silver", 300, "\U0001f948"),
    ("Gold", 800, "\U0001f947"),
]

TIER_EARN_MULTIPLIER = {"Bronze": 1.0, "Silver": 1.2, "Gold": 1.5}


def singapore_now_iso():
    return datetime.now(SINGAPORE_TZ).isoformat(timespec="seconds")


def _rollback_on_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            db.session.rollback()
            raise

    wrapper.__name__ = func.__name__
    return wrapper


# ---------------------------------------------------------------------
# Pure calculations kept alongside the data they operate on, so
# repository functions (award_loyalty_points, redeem/checkout flows) don't
# need to import from app.py (which imports this module) — app.py imports
# these from here too, so there is exactly one copy of the logic.
# ---------------------------------------------------------------------

def _parse_booking_date(date_value):
    if not date_value:
        return None
    try:
        return datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_booking_length(checkin_date, checkout_date):
    checkin = _parse_booking_date(checkin_date)
    checkout = _parse_booking_date(checkout_date)
    if checkin and checkout and checkout > checkin:
        return (checkout - checkin).days
    return None


def calculate_loyalty_points(room_type, nights):
    if not nights or nights <= 0:
        return 0
    return LOYALTY_POINTS_PER_NIGHT.get(room_type, 0) * nights


def calculate_points_discount(points_to_redeem, booking_total):
    if not points_to_redeem or points_to_redeem <= 0 or not booking_total or booking_total <= 0:
        return 0, 0.0
    requested_discount = points_to_redeem / LOYALTY_POINTS_PER_DOLLAR
    discount = min(requested_discount, booking_total)
    points_used = int(discount * LOYALTY_POINTS_PER_DOLLAR)
    return points_used, round(points_used / LOYALTY_POINTS_PER_DOLLAR, 2)


def get_user_tier(lifetime_points):
    tier_name, icon = LOYALTY_TIERS[0][0], LOYALTY_TIERS[0][2]
    points_to_next = None
    next_tier_name = None

    for index, (name, threshold, tier_icon) in enumerate(LOYALTY_TIERS):
        if lifetime_points >= threshold:
            tier_name, icon = name, tier_icon
            if index + 1 < len(LOYALTY_TIERS):
                next_tier_name = LOYALTY_TIERS[index + 1][0]
                points_to_next = LOYALTY_TIERS[index + 1][1] - lifetime_points
            else:
                next_tier_name = None
                points_to_next = None
        else:
            break

    return tier_name, icon, points_to_next, next_tier_name


def get_tier_overview():
    return [
        {"name": name, "icon": icon, "threshold": threshold, "multiplier": TIER_EARN_MULTIPLIER.get(name, 1.0)}
        for name, threshold, icon in LOYALTY_TIERS
    ]


def get_room_image(room_type, room_number="", room_id=0):
    image_pool = ROOM_IMAGE_POOLS.get(room_type, ROOM_IMAGE_POOLS["Single"])
    try:
        number = int(str(room_number).strip())
    except (TypeError, ValueError):
        return image_pool[0]

    if room_type == "Single" and 1 <= number <= 40 and number % 2 == 0:
        category_index = (number // 2) - 1
    elif room_type == "Double" and 1 <= number <= 40 and number % 2 == 1:
        category_index = (number - 1) // 2
    elif room_type == "Suite" and 41 <= number <= 50:
        category_index = number - 41
    else:
        category_index = 0

    return image_pool[category_index % len(image_pool)]


def derive_room_details(room_number):
    try:
        number = int(str(room_number).strip())
    except (TypeError, ValueError):
        return None
    if number < 1 or number > 50:
        return None

    if number <= 40:
        if number % 2 == 0:
            room_type, price = "Single", 100
        else:
            room_type, price = "Double", 200
    else:
        room_type, price = "Suite", 500

    return {
        "number": number,
        "room_number": str(number),
        "type": room_type,
        "price": price,
        "status": "Available",
        "image": get_room_image(room_type, number),
    }


@lru_cache(maxsize=1)
def get_seed_room_numbers():
    """Permanent seed room numbers from data.json (not a DB column)."""
    payload = json.loads(DATA_JSON_PATH.read_text(encoding="utf-8"))
    numbers = []
    for record in payload.get("rooms") or []:
        try:
            numbers.append(int(record["room_number"]))
        except (KeyError, TypeError, ValueError):
            continue
    return frozenset(numbers)


def is_seed_room_number(room_number):
    try:
        number = int(str(room_number).strip())
    except (TypeError, ValueError):
        return False
    return number in get_seed_room_numbers()


def room_has_booking_records(room_id):
    count = db.session.execute(
        db.select(db.func.count()).select_from(Booking).filter_by(room_id=room_id)
    ).scalar_one()
    return int(count) > 0


def _active_booking_statuses_for_room(room_id):
    return {
        row[0]
        for row in db.session.execute(
            db.select(Booking.status).filter(
                Booking.room_id == room_id,
                Booking.status.in_(("Booked", "Checked In")),
            )
        ).all()
    }


def validate_manual_room_status_change(room_id, new_status):
    """Block admin status changes that contradict active booking/check-in state."""
    if new_status not in ALLOWED_ROOM_STATUSES:
        return "Please select Available, Booked or Maintenance."
    active = _active_booking_statuses_for_room(room_id)
    if new_status == "Available" and active:
        return (
            "Cannot set Available while the room has an active booking. "
            "Cancel or check out the booking first, or set Maintenance if the room needs work."
        )
    if new_status == "Maintenance" and "Checked In" in active:
        return "Cannot set Maintenance while a guest is checked in."
    return None


def can_delete_room(room_id):
    """Return (ok, error_message). Seed rooms and rooms with booking history are protected."""
    room = db.session.get(Room, room_id)
    if room is None:
        return False, "Room not found"
    if is_seed_room_number(room.room_number):
        return (
            False,
            f"Room {room.room_number} is a permanent seed room and cannot be deleted. "
            "Set Maintenance instead if it should be unavailable.",
        )
    if room_has_booking_records(room_id):
        return (
            False,
            f"Room {room.room_number} has booking history and cannot be deleted. "
            "Set Maintenance instead.",
        )
    return True, None


# ---------------------------------------------------------------------
# users
# ---------------------------------------------------------------------

def get_user(username):
    if not username:
        return None
    user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    return user.to_dict() if user else None


def list_users():
    return [u.to_dict() for u in db.session.execute(db.select(User)).scalars().all()]


def username_exists(username):
    return db.session.execute(db.select(User.id).filter_by(username=username)).scalar_one_or_none() is not None


@_rollback_on_error
def create_user(username, password_hash, role="user"):
    user = User(username=username, password_hash=password_hash, role=role, points=0)
    db.session.add(user)
    db.session.commit()
    return user.to_dict()


@_rollback_on_error
def update_user_password(username, password_hash):
    user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if user is None:
        return False
    user.password_hash = password_hash
    db.session.commit()
    return True


@_rollback_on_error
def set_user_last_seen_tier(username, tier_name):
    user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if user is not None:
        user.last_seen_tier = tier_name
        db.session.commit()


def get_user_lifetime_points(username):
    """Total points a guest has ever earned or been credited (ignores redemptions)."""
    from_bookings = db.session.execute(
        db.select(db.func.coalesce(db.func.sum(Booking.points_earned), 0))
        .filter(Booking.username == username, Booking.points_awarded.is_(True))
    ).scalar_one()
    from_adjustments = db.session.execute(
        db.select(db.func.coalesce(db.func.sum(LoyaltyPoint.points), 0))
        .filter(LoyaltyPoint.username == username, LoyaltyPoint.points > 0)
    ).scalar_one()
    return int(from_bookings) + int(from_adjustments)


@_rollback_on_error
def adjust_user_points(username, points, reason, admin_username):
    """Manually add/subtract a guest's balance (clamped at 0) and log the ledger entry."""
    user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if user is None:
        return None

    user.points = max(0, user.points + points)
    entry = LoyaltyPoint(
        username=username,
        admin_username=admin_username,
        points=points,
        reason=reason,
        is_expiry=False,
        created_at=datetime.now(SINGAPORE_TZ).replace(tzinfo=None),
    )
    db.session.add(entry)
    db.session.commit()
    return entry.to_dict()


def get_user_points_ledger(username):
    """Return the given user's loyalty point events (earned + redeemed + adjusted), newest first."""
    entries = []

    user_bookings = db.session.execute(db.select(Booking).filter_by(username=username)).scalars().all()
    for booking in user_bookings:
        b = booking.to_dict()
        nights = get_booking_length(b.get("checkin_date"), b.get("checkout_date"))
        nights_label = f"{nights} night{'s' if nights != 1 else ''}" if nights else "N/A"
        room_label = f"Room {b.get('room_number', 'N/A')}"
        stay_label = f"{b.get('checkin_date', '?')} to {b.get('checkout_date', '?')}"

        if b.get("points_redeemed"):
            created_at = b.get("created_at") or _date_to_midnight_iso(b.get("checkin_date"))
            entries.append({
                "date": created_at or "",
                "type": "Redeemed",
                "nights_label": nights_label,
                "room_type": b.get("room_type", "N/A"),
                "points": -b.get("points_redeemed", 0),
                "description": f"Redeemed on booking - {room_label} ({stay_label})",
            })

        if b.get("points_awarded"):
            description = f"Earned from stay - {room_label} ({stay_label})"
            points_base = b.get("points_base")
            points_tier = b.get("points_tier")
            if points_base and points_tier and b.get("points_earned", 0) != points_base:
                multiplier = TIER_EARN_MULTIPLIER.get(points_tier, 1.0)
                description += f" · {points_base} base × {multiplier}x {points_tier} bonus"

            checked_out_at = b.get("checked_out_at") or _date_to_midnight_iso(b.get("checkout_date"))
            entries.append({
                "date": checked_out_at or "",
                "type": "Earned",
                "nights_label": nights_label,
                "room_type": b.get("room_type", "N/A"),
                "points": b.get("points_earned", 0),
                "description": description,
            })

    adjustments = db.session.execute(db.select(LoyaltyPoint).filter_by(username=username)).scalars().all()
    for adjustment in adjustments:
        a = adjustment.to_dict()
        entries.append({
            "date": a.get("created_at") or "",
            "type": "Expired" if a.get("is_expiry") else "Adjusted",
            "nights_label": "—",
            "room_type": "—",
            "points": a.get("points", 0),
            "description": a.get("reason", "") if a.get("is_expiry")
            else f"Manual adjustment by {a.get('admin_username', 'admin')}: {a.get('reason', '')}",
        })

    entries.sort(key=lambda entry: entry.get("date") or "", reverse=True)
    return entries


def _date_to_midnight_iso(date_value):
    parsed = _parse_booking_date(date_value)
    return parsed.strftime("%Y-%m-%dT00:00:00") if parsed else None


def _parse_ledger_date(date_value):
    if not date_value:
        return None
    try:
        return datetime.fromisoformat(date_value).date()
    except ValueError:
        return _parse_booking_date(date_value)


@_rollback_on_error
def expire_stale_points(username, today=None):
    """Forfeit a guest's spendable balance after a year of no loyalty activity. Returns True if expired."""
    user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if user is None or user.points <= 0:
        return False

    ledger = get_user_points_ledger(username)
    if not ledger:
        return False

    last_activity = _parse_ledger_date(ledger[0].get("date"))
    if not last_activity:
        return False

    if today is None:
        today = datetime.now(SINGAPORE_TZ).date()
    if (today - last_activity).days < POINTS_EXPIRY_DAYS:
        return False

    expired_points = user.points
    user.points = 0
    db.session.add(
        LoyaltyPoint(
            username=username,
            admin_username="system",
            points=-expired_points,
            reason=f"{expired_points} points expired after {POINTS_EXPIRY_DAYS} days of no loyalty activity.",
            is_expiry=True,
            created_at=datetime.now(SINGAPORE_TZ).replace(tzinfo=None),
        )
    )
    db.session.commit()
    return True


def list_loyalty_adjustments():
    return [a.to_dict() for a in db.session.execute(db.select(LoyaltyPoint)).scalars().all()]


# ---------------------------------------------------------------------
# rooms
# ---------------------------------------------------------------------

def list_rooms():
    rooms = db.session.execute(db.select(Room)).scalars().all()
    return sorted((r.to_dict() for r in rooms), key=lambda room: int(room["room_number"]))


def get_room(room_id):
    room = db.session.get(Room, room_id)
    return room.to_dict() if room else None


def get_existing_room_numbers(exclude_room_id=None):
    query = db.select(Room.room_number)
    if exclude_room_id is not None:
        query = query.filter(Room.id != exclude_room_id)
    return sorted(row[0] for row in db.session.execute(query).all())


@_rollback_on_error
def create_room(room_number, status="Available"):
    details = derive_room_details(room_number)
    if details is None:
        return None
    if status not in ALLOWED_ROOM_STATUSES:
        status = "Available"

    room = Room(
        room_number=details["number"],
        room_type=details["type"],
        price=details["price"],
        status=status,
        image_url=details["image"],
    )
    db.session.add(room)
    db.session.commit()
    return room.to_dict()


@_rollback_on_error
def update_room(room_id, room_number, status):
    room = db.session.get(Room, room_id)
    if room is None:
        return None
    details = derive_room_details(room_number)
    if details is None:
        return None
    if status not in ALLOWED_ROOM_STATUSES:
        return None

    room.room_number = details["number"]
    room.room_type = details["type"]
    room.price = details["price"]
    room.status = status
    room.image_url = details["image"]
    db.session.commit()
    return room.to_dict()


@_rollback_on_error
def delete_room(room_id):
    """Hard-delete only when can_delete_room allows it. Returns the deleted room dict or None."""
    ok, _error = can_delete_room(room_id)
    if not ok:
        return None
    room = db.session.get(Room, room_id)
    if room is None:
        return None
    payload = room.to_dict()
    db.session.delete(room)
    db.session.commit()
    return payload


@_rollback_on_error
def set_room_status(room_id, status):
    room = db.session.get(Room, room_id)
    if room is None or status not in ALLOWED_ROOM_STATUSES:
        return None
    conflict = validate_manual_room_status_change(room_id, status)
    if conflict:
        return None
    room.status = status
    db.session.commit()
    return room.to_dict()


def _sync_room_status(room):
    """Recompute a room's status from its own current bookings (no commit — caller commits)."""
    if room is None or room.status == "Maintenance":
        return
    statuses = {
        row[0]
        for row in db.session.execute(db.select(Booking.status).filter_by(room_id=room.id)).all()
    }
    if "Checked In" in statuses:
        room.status = "Occupied"
    elif "Booked" in statuses:
        room.status = "Booked"
    else:
        room.status = "Available"


@_rollback_on_error
def sync_room_status(room_id):
    if room_id is None:
        return
    room = db.session.get(Room, room_id)
    _sync_room_status(room)
    db.session.commit()


def filter_rooms_by_type(room_list, room_type):
    if not room_type:
        return list(room_list)
    selected = str(room_type).strip().lower()
    return [room for room in room_list if str(room.get("type", "")).strip().lower() == selected]


# ---------------------------------------------------------------------
# bookings
# ---------------------------------------------------------------------

def list_bookings():
    return [b.to_dict() for b in db.session.execute(db.select(Booking)).scalars().all()]


def get_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    return booking.to_dict() if booking else None


def get_user_bookings(username):
    return [b.to_dict() for b in db.session.execute(db.select(Booking).filter_by(username=username)).scalars().all()]


def get_user_room_number(username):
    booking = db.session.execute(
        db.select(Booking).filter_by(username=username).order_by(Booking.id.desc())
    ).scalars().first()
    return str(booking.room_number) if booking else "N/A"


def is_room_available(room_id, checkin_date, checkout_date, exclude_booking_id=None):
    requested_ci = _parse_booking_date(checkin_date)
    requested_co = _parse_booking_date(checkout_date)
    if not requested_ci or not requested_co:
        return False

    query = db.select(Booking).filter(
        Booking.room_id == room_id,
        Booking.status.notin_(["Checked Out", "Cancelled", "No-Show"]),
    )
    if exclude_booking_id is not None:
        query = query.filter(Booking.id != exclude_booking_id)

    for booking in db.session.execute(query).scalars().all():
        if not (requested_co <= booking.checkin_date or requested_ci >= booking.checkout_date):
            return False
    return True


@_rollback_on_error
def create_booking(
    room_id, room_number, room_type, price, checkin_date, checkout_date, username,
    guest_first_name, guest_last_name, phone_number, email,
    points_redeemed=0, points_discount=0.0, total_price=None,
):
    """Insert a booking, deduct any redeemed points, and refresh the room's status — one transaction."""
    guest_name = " ".join(part for part in [guest_first_name.strip(), guest_last_name.strip()] if part)

    if points_redeemed:
        user = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
        if user is not None:
            user.points = user.points - points_redeemed

    booking = Booking(
        username=username,
        guest_first_name=guest_first_name.strip(),
        guest_last_name=guest_last_name.strip(),
        guest_name=guest_name,
        phone_number=phone_number.strip(),
        email=email.strip(),
        room_id=room_id,
        room_number=int(room_number),
        room_type=room_type,
        price=price,
        checkin_date=_parse_booking_date(checkin_date),
        checkout_date=_parse_booking_date(checkout_date),
        status="Booked",
        points_redeemed=points_redeemed,
        points_discount=points_discount,
        total_price=total_price if total_price is not None else price,
        created_at=datetime.now(SINGAPORE_TZ).replace(tzinfo=None),
    )
    db.session.add(booking)
    db.session.flush()

    room = db.session.get(Room, room_id)
    _sync_room_status(room)

    db.session.commit()
    return booking.to_dict()


@_rollback_on_error
def cancel_booking(booking_id, username):
    """Guest cancels their own still-Booked reservation."""
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.username != username or booking.status != "Booked":
        return False
    booking.status = "Cancelled"
    _sync_room_status(db.session.get(Room, booking.room_id) if booking.room_id else None)
    db.session.commit()
    return True


@_rollback_on_error
def mark_no_show(booking_id, today=None):
    booking = db.session.get(Booking, booking_id)
    if today is None:
        today = datetime.now().date()
    if booking is None or booking.status != "Booked" or booking.checkin_date is None or booking.checkin_date >= today:
        return False
    booking.status = "No-Show"
    _sync_room_status(db.session.get(Room, booking.room_id) if booking.room_id else None)
    db.session.commit()
    return True


@_rollback_on_error
def checkin_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.status != "Booked":
        return False
    booking.status = "Checked In"
    _sync_room_status(db.session.get(Room, booking.room_id) if booking.room_id else None)
    db.session.commit()
    return True


@_rollback_on_error
def checkout_booking(booking_id):
    """Check a guest out and award loyalty points for the stay in one transaction. Returns points awarded (0 if none/ineligible)."""
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.status != "Checked In":
        return None

    booking.status = "Checked Out"
    booking.checked_out_at = datetime.now(SINGAPORE_TZ).replace(tzinfo=None)
    _sync_room_status(db.session.get(Room, booking.room_id) if booking.room_id else None)

    points_awarded = 0
    if not booking.points_awarded:
        nights = get_booking_length(
            booking.checkin_date.strftime("%Y-%m-%d") if booking.checkin_date else None,
            booking.checkout_date.strftime("%Y-%m-%d") if booking.checkout_date else None,
        )
        base_points = calculate_loyalty_points(booking.room_type, nights)

        lifetime = get_user_lifetime_points(booking.username)
        tier_name, _, _, _ = get_user_tier(lifetime)
        multiplier = TIER_EARN_MULTIPLIER.get(tier_name, 1.0)
        points_awarded = round(base_points * multiplier)

        user = db.session.execute(db.select(User).filter_by(username=booking.username)).scalar_one_or_none()
        if user is not None:
            user.points = user.points + points_awarded

        booking.points_awarded = True
        booking.points_earned = points_awarded
        booking.points_base = base_points
        booking.points_tier = tier_name

    db.session.commit()
    return points_awarded


@_rollback_on_error
def archive_booking(booking_id, archived=True):
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        return False
    if archived and (booking.status or "Booked") not in ARCHIVABLE_BOOKING_STATUSES:
        return False
    booking.archived = archived
    db.session.commit()
    return True


@_rollback_on_error
def mark_points_earned_seen(booking_ids):
    if not booking_ids:
        return
    bookings = db.session.execute(db.select(Booking).filter(Booking.id.in_(booking_ids))).scalars().all()
    for booking in bookings:
        booking.points_earned_seen = True
    db.session.commit()


@_rollback_on_error
def update_booking_guest_details(booking_id, guest_first_name, guest_last_name, phone_number, email, checkin_date, checkout_date):
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        return False
    booking.guest_first_name = guest_first_name
    booking.guest_last_name = guest_last_name
    booking.guest_name = " ".join(part for part in [guest_first_name, guest_last_name] if part)
    booking.phone_number = phone_number
    booking.email = email
    booking.checkin_date = _parse_booking_date(checkin_date)
    booking.checkout_date = _parse_booking_date(checkout_date)
    db.session.commit()
    return True


@_rollback_on_error
def remove_past_bookings(today=None):
    if today is None:
        today = datetime.now().date()
    stale = db.session.execute(db.select(Booking).filter(Booking.checkout_date < today)).scalars().all()
    count = len(stale)
    for booking in stale:
        db.session.delete(booking)
    db.session.commit()
    return count


def filter_bookings(bookings_list, search="", status="", room_type="", checkin_date="", checkout_date="", archived=None):
    search = (search or "").strip().lower()
    status = (status or "").strip()
    room_type = (room_type or "").strip()
    checkin_date = (checkin_date or "").strip()
    checkout_date = (checkout_date or "").strip()

    def matches_search(booking):
        if not search:
            return True
        haystack = (
            str(booking.get("guest_name", "")),
            str(booking.get("id", "")),
            str(booking.get("room_number", "")),
            str(booking.get("phone_number", "")),
            str(booking.get("email", "")),
        )
        return any(search in field.lower() for field in haystack)

    filtered = []
    for booking in bookings_list:
        if not matches_search(booking):
            continue
        if status and (booking.get("status") or "Booked") != status:
            continue
        if room_type and booking.get("room_type") != room_type:
            continue
        if checkin_date and booking.get("checkin_date") != checkin_date:
            continue
        if checkout_date and booking.get("checkout_date") != checkout_date:
            continue
        if archived is not None and bool(booking.get("archived")) != archived:
            continue
        filtered.append(booking)
    return filtered


# ---------------------------------------------------------------------
# feedback
# ---------------------------------------------------------------------

def feedback_exists_for_booking(booking_id):
    return db.session.execute(
        db.select(Feedback.id).filter_by(booking_id=booking_id)
    ).scalar_one_or_none() is not None


def get_user_feedback_booking_options(username):
    options = []
    user_bookings = db.session.execute(
        db.select(Booking).filter_by(username=username)
    ).scalars().all()
    for booking in user_bookings:
        if booking.id is None or feedback_exists_for_booking(booking.id):
            continue
        room_number = booking.room_number
        if not room_number:
            continue
        guest_name = booking.guest_name or "Guest"
        options.append({
            "value": booking.id,
            "label": (
                f"Room {room_number} - {guest_name} "
                f"({booking.checkin_date} to {booking.checkout_date})"
            ),
            "guest_name": guest_name,
            "room_number": str(room_number),
            "room_type": booking.room_type,
            "checkin_date": booking.checkin_date.strftime("%Y-%m-%d") if booking.checkin_date else "",
            "checkout_date": booking.checkout_date.strftime("%Y-%m-%d") if booking.checkout_date else "",
            "username": booking.username,
        })
    return list(reversed(options))


@_rollback_on_error
def create_feedback(booking_id, username, guest_name, room_number, room_type, checkin_date, checkout_date,
                     facilities_rating, amenities_rating, comfort_cleanliness_rating, additional_feedback):
    entry = Feedback(
        booking_id=booking_id,
        username=username,
        guest_name=guest_name,
        room_number=int(room_number),
        room_type=room_type,
        checkin_date=_parse_booking_date(checkin_date),
        checkout_date=_parse_booking_date(checkout_date),
        facilities_rating=facilities_rating,
        amenities_rating=amenities_rating,
        comfort_cleanliness_rating=comfort_cleanliness_rating,
        additional_feedback=additional_feedback,
        submitted_at=datetime.now(SINGAPORE_TZ).replace(tzinfo=None),
    )
    db.session.add(entry)
    db.session.commit()
    return entry.to_dict()


def get_sorted_feedback():
    entries = [f.to_dict() for f in db.session.execute(db.select(Feedback)).scalars().all()]
    return sorted(entries, key=lambda entry: entry.get("submitted_at", ""), reverse=True)


def feedback_owned_by_user(entry, username):
    if not entry or entry.get("username") != username:
        return False
    booking = db.session.get(Booking, entry.get("booking_id"))
    return booking is not None and booking.username == username


def get_user_submitted_feedback(username):
    entries = [
        f.to_dict()
        for f in db.session.execute(db.select(Feedback).filter_by(username=username)).scalars().all()
    ]
    return sorted(entries, key=lambda entry: entry.get("submitted_at", ""), reverse=True)


def get_owned_feedback_by_id(feedback_id, username):
    entry = db.session.get(Feedback, feedback_id)
    if entry is None:
        return None
    entry_dict = entry.to_dict()
    return entry_dict if feedback_owned_by_user(entry_dict, username) else None


# ---------------------------------------------------------------------
# reservation_requests
# ---------------------------------------------------------------------

def list_requests():
    return [r.to_dict() for r in db.session.execute(db.select(ReservationRequest)).scalars().all()]


def get_user_requests(username):
    return [
        r.to_dict()
        for r in db.session.execute(db.select(ReservationRequest).filter_by(username=username)).scalars().all()
    ]


def get_request(request_id):
    entry = db.session.get(ReservationRequest, request_id)
    return entry.to_dict() if entry else None


def get_user_booked_room_options(username):
    options = []
    user_bookings = db.session.execute(
        db.select(Booking).filter_by(username=username, status="Checked In")
    ).scalars().all()
    for booking in user_bookings:
        room_number = booking.room_number
        guest_name = booking.guest_name or "Guest"
        if room_number:
            options.append({
                "value": str(room_number),
                "label": f"Room {room_number} - {guest_name}",
                "guest_name": guest_name,
            })
    return options


def get_room_options():
    options = []
    for room in db.session.execute(db.select(Room)).scalars().all():
        options.append({
            "value": str(room.room_number),
            "label": f"Room {room.room_number} ({room.room_type}) - {room.status}",
        })
    return sorted(options, key=lambda opt: opt["value"])


@_rollback_on_error
def create_reservation_request(username, room_number, room_type, category, message, guest_name,
                                priority, estimated_min, estimated_max, estimated_time):
    entry = ReservationRequest(
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
        status="Pending",
        created_at=datetime.now(SINGAPORE_TZ).replace(tzinfo=None),
    )
    db.session.add(entry)
    db.session.flush()
    entry.queue_ticket = f"#{entry.id:03d}"
    db.session.commit()
    return entry.to_dict()


@_rollback_on_error
def accept_request(request_id, estimate_fn):
    entry = db.session.get(ReservationRequest, request_id)
    if entry is None or entry.status != "Pending":
        return False
    entry.status = "Accepted"
    if entry.estimated_time is None:
        estimated_min, estimated_max, peak_desc = estimate_fn(entry.message or "")
        entry.estimated_time = f"{estimated_min}-{estimated_max} minutes ({peak_desc})"
        entry.estimated_min = estimated_min
        entry.estimated_max = estimated_max
    db.session.commit()
    return True


@_rollback_on_error
def accept_all_requests(estimate_fn):
    pending = db.session.execute(db.select(ReservationRequest).filter_by(status="Pending")).scalars().all()
    accepted_count = 0
    for entry in pending:
        entry.status = "Accepted"
        if entry.estimated_time is None:
            estimated_min, estimated_max, peak_desc = estimate_fn(entry.message or "")
            entry.estimated_time = f"{estimated_min}-{estimated_max} minutes ({peak_desc})"
            entry.estimated_min = estimated_min
            entry.estimated_max = estimated_max
        accepted_count += 1
    db.session.commit()
    return accepted_count


@_rollback_on_error
def cancel_user_request(request_id, username):
    entry = db.session.get(ReservationRequest, request_id)
    if entry is None or entry.username != username or entry.status != "Pending":
        return False
    entry.status = "Cancelled"
    entry.cancelled_by = username
    db.session.commit()
    return True


@_rollback_on_error
def mark_request_received(request_id, username):
    entry = db.session.get(ReservationRequest, request_id)
    if entry is None or entry.username != username or entry.status != "Accepted":
        return False
    entry.received = True
    db.session.commit()
    return True
