"""One-time migration of data.json into MySQL.

Usage (PowerShell, from the project root):
    python scripts\\migrate_json_to_mysql.py

Reads data.json (left untouched — it stays on disk as a legacy backup) and
inserts its records into the MySQL tables created by scripts\\init_db.py, in
foreign-key-safe order: users -> rooms -> bookings -> feedback ->
loyalty_points. reservation_requests is never present in data.json (that
data was never actually persisted to JSON in the old app) so nothing is
migrated for it.

Safe to re-run: records already present (matched by id, or by username for
users) are skipped, never duplicated. Every record that fails validation is
printed individually with the reason and skipped — never silently dropped.
Exits with a clear error if MySQL can't be reached.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from config import Config, ConfigError
from models import Booking, Feedback, LoyaltyPoint, Room, User, db
from seed_dev_users import ensure_seed_accounts

DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json"
)

ROOM_TYPES = {"Single", "Double", "Suite"}
ROOM_STATUSES = {"Available", "Booked", "Occupied", "Maintenance"}
BOOKING_STATUSES = {"Booked", "Checked In", "Checked Out", "Cancelled", "No-Show"}


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def parse_datetime(value, fallback_date=None):
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.replace(tzinfo=None)
        except (TypeError, ValueError):
            pass
    if fallback_date:
        return datetime.combine(fallback_date, datetime.min.time())
    return None


class Summary:
    def __init__(self, name):
        self.name = name
        self.migrated = 0
        self.skipped_existing = 0
        self.invalid = 0

    def line(self):
        return f"  {self.name}: {self.migrated} migrated, {self.skipped_existing} already present, {self.invalid} invalid/skipped"


def migrate_users(data, summary):
    known_usernames = {row[0] for row in db.session.execute(db.select(User.username)).all()}

    for record in data.get("users", []):
        username = str(record.get("username") or "").strip()
        if not username:
            print("INVALID user record: missing username")
            summary.invalid += 1
            continue
        if username in known_usernames:
            summary.skipped_existing += 1
            continue

        password_hash = record.get("password_hash")
        if not password_hash:
            plain_password = record.get("password")
            if not plain_password:
                print(f"INVALID user '{username}': no password_hash or password field")
                summary.invalid += 1
                continue
            password_hash = generate_password_hash(plain_password)

        db.session.add(
            User(
                username=username,
                password_hash=password_hash,
                role="user",
                points=0,
                last_seen_tier=record.get("last_seen_tier"),
            )
        )
        known_usernames.add(username)
        summary.migrated += 1

    db.session.commit()

    # Overlay data.json's separate user_points / user_last_seen_tier maps
    # (authoritative balance/tier storage in the old app) onto every user,
    # matched case-insensitively by username, exactly like load_data() did.
    user_points = data.get("user_points", {})
    user_last_seen_tier = data.get("user_last_seen_tier", {})
    if isinstance(user_points, dict) or isinstance(user_last_seen_tier, dict):
        all_users = db.session.execute(db.select(User)).scalars().all()
        for user in all_users:
            key = user.username.lower()
            if isinstance(user_points, dict) and key in user_points:
                user.points = user_points[key]
            if isinstance(user_last_seen_tier, dict) and key in user_last_seen_tier:
                user.last_seen_tier = user_last_seen_tier[key]
        db.session.commit()


def migrate_rooms(data, summary):
    known_ids = {row[0] for row in db.session.execute(db.select(Room.id)).all()}

    for record in data.get("rooms", []):
        room_id = record.get("id")
        if room_id is None:
            print("INVALID room record: missing id")
            summary.invalid += 1
            continue
        if room_id in known_ids:
            summary.skipped_existing += 1
            continue

        try:
            room_number = int(record.get("room_number"))
        except (TypeError, ValueError):
            print(f"INVALID room id={room_id}: room_number is not a valid integer")
            summary.invalid += 1
            continue

        room_type = record.get("type")
        status = record.get("status", "Available")
        if room_type not in ROOM_TYPES:
            print(f"INVALID room id={room_id}: room_type '{room_type}' is not one of {sorted(ROOM_TYPES)}")
            summary.invalid += 1
            continue
        if status not in ROOM_STATUSES:
            print(f"INVALID room id={room_id}: status '{status}' is not one of {sorted(ROOM_STATUSES)}")
            summary.invalid += 1
            continue

        db.session.add(
            Room(
                id=room_id,
                room_number=room_number,
                room_type=room_type,
                price=record.get("price", 0),
                status=status,
                image_url=record.get("image"),
            )
        )
        known_ids.add(room_id)
        summary.migrated += 1

    db.session.commit()


def migrate_bookings(data, summary):
    known_ids = {row[0] for row in db.session.execute(db.select(Booking.id)).all()}
    known_usernames = {row[0] for row in db.session.execute(db.select(User.username)).all()}
    known_room_ids = {row[0] for row in db.session.execute(db.select(Room.id)).all()}

    for record in data.get("bookings", []):
        booking_id = record.get("id")
        if booking_id is None:
            print("INVALID booking record: missing id")
            summary.invalid += 1
            continue
        if booking_id in known_ids:
            summary.skipped_existing += 1
            continue

        username = record.get("username")
        if username not in known_usernames:
            print(f"INVALID booking id={booking_id}: username '{username}' does not exist in users table")
            summary.invalid += 1
            continue

        checkin = parse_date(record.get("checkin_date"))
        checkout = parse_date(record.get("checkout_date"))
        if not checkin or not checkout:
            print(f"INVALID booking id={booking_id}: unparseable checkin/checkout date")
            summary.invalid += 1
            continue

        status = record.get("status") or "Booked"
        if status not in BOOKING_STATUSES:
            print(f"INVALID booking id={booking_id}: status '{status}' is not one of {sorted(BOOKING_STATUSES)}")
            summary.invalid += 1
            continue

        room_id = record.get("room_id")
        if room_id is not None and room_id not in known_room_ids:
            print(f"WARNING booking id={booking_id}: room_id {room_id} not found — migrating with room_id=NULL")
            room_id = None

        price = record.get("price", 0)
        created_at = parse_datetime(record.get("created_at"), fallback_date=checkin)

        db.session.add(
            Booking(
                id=booking_id,
                username=username,
                guest_first_name=record.get("guest_first_name", ""),
                guest_last_name=record.get("guest_last_name", ""),
                guest_name=record.get("guest_name", ""),
                phone_number=record.get("phone_number", ""),
                email=record.get("email", ""),
                room_id=room_id,
                room_number=int(record.get("room_number")),
                room_type=record.get("room_type", ""),
                price=price,
                checkin_date=checkin,
                checkout_date=checkout,
                status=status,
                points_redeemed=record.get("points_redeemed", 0),
                points_discount=record.get("points_discount", 0),
                total_price=record.get("total_price", price),
                points_awarded=bool(record.get("points_awarded", False)),
                points_earned=record.get("points_earned", 0),
                points_base=record.get("points_base"),
                points_tier=record.get("points_tier"),
                points_earned_seen=bool(record.get("points_earned_seen", False)),
                archived=bool(record.get("archived", False)),
                created_at=created_at,
                checked_out_at=parse_datetime(record.get("checked_out_at")),
            )
        )
        known_ids.add(booking_id)
        summary.migrated += 1

    db.session.commit()


def migrate_feedback(data, summary):
    known_ids = {row[0] for row in db.session.execute(db.select(Feedback.id)).all()}
    known_usernames = {row[0] for row in db.session.execute(db.select(User.username)).all()}
    known_booking_ids = {row[0] for row in db.session.execute(db.select(Booking.id)).all()}

    for record in data.get("feedback", []):
        feedback_id = record.get("id")
        if feedback_id is None:
            print("INVALID feedback record: missing id")
            summary.invalid += 1
            continue
        if feedback_id in known_ids:
            summary.skipped_existing += 1
            continue

        booking_id = record.get("booking_id")
        username = record.get("username")
        if booking_id not in known_booking_ids:
            print(f"INVALID feedback id={feedback_id}: booking_id {booking_id} does not exist")
            summary.invalid += 1
            continue
        if username not in known_usernames:
            print(f"INVALID feedback id={feedback_id}: username '{username}' does not exist in users table")
            summary.invalid += 1
            continue

        ratings = {
            "facilities_rating": record.get("facilities_rating"),
            "amenities_rating": record.get("amenities_rating"),
            "comfort_cleanliness_rating": record.get("comfort_cleanliness_rating"),
        }
        if any(not isinstance(v, int) or not (1 <= v <= 5) for v in ratings.values()):
            print(f"INVALID feedback id={feedback_id}: ratings must be whole numbers from 1 to 5")
            summary.invalid += 1
            continue

        checkin = parse_date(record.get("checkin_date"))
        checkout = parse_date(record.get("checkout_date"))
        if not checkin or not checkout:
            print(f"INVALID feedback id={feedback_id}: unparseable checkin/checkout date")
            summary.invalid += 1
            continue

        db.session.add(
            Feedback(
                id=feedback_id,
                booking_id=booking_id,
                username=username,
                guest_name=record.get("guest_name", ""),
                room_number=int(record.get("room_number")),
                room_type=record.get("room_type", ""),
                checkin_date=checkin,
                checkout_date=checkout,
                additional_feedback=record.get("additional_feedback", ""),
                submitted_at=parse_datetime(record.get("submitted_at"), fallback_date=checkout),
                **ratings,
            )
        )
        known_ids.add(feedback_id)
        summary.migrated += 1

    db.session.commit()


def migrate_loyalty_points(data, summary):
    known_ids = {row[0] for row in db.session.execute(db.select(LoyaltyPoint.id)).all()}
    known_usernames = {row[0] for row in db.session.execute(db.select(User.username)).all()}

    for record in data.get("points_adjustments", []):
        entry_id = record.get("id")
        if entry_id is None:
            print("INVALID loyalty_points record: missing id")
            summary.invalid += 1
            continue
        if entry_id in known_ids:
            summary.skipped_existing += 1
            continue

        username = record.get("username")
        if username not in known_usernames:
            print(f"INVALID loyalty_points id={entry_id}: username '{username}' does not exist in users table")
            summary.invalid += 1
            continue

        db.session.add(
            LoyaltyPoint(
                id=entry_id,
                username=username,
                admin_username=record.get("admin_username", "system"),
                points=record.get("points", 0),
                reason=record.get("reason", ""),
                is_expiry=bool(record.get("is_expiry", False)),
                created_at=parse_datetime(record.get("created_at")),
            )
        )
        known_ids.add(entry_id)
        summary.migrated += 1

    db.session.commit()


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

        if not os.path.exists(DEFAULT_JSON_PATH):
            print(f"No data.json found at {DEFAULT_JSON_PATH} — nothing to migrate.")
            return

        with open(DEFAULT_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        print("Ensuring development seed accounts exist (admin/user) ...")
        ensure_seed_accounts()
        print()

        summaries = {
            "users": Summary("users"),
            "rooms": Summary("rooms"),
            "bookings": Summary("bookings"),
            "feedback": Summary("feedback"),
            "loyalty_points": Summary("loyalty_points"),
        }

        print("Migrating users ...")
        migrate_users(data, summaries["users"])
        print("Migrating rooms ...")
        migrate_rooms(data, summaries["rooms"])
        print("Migrating bookings ...")
        migrate_bookings(data, summaries["bookings"])
        print("Migrating feedback ...")
        migrate_feedback(data, summaries["feedback"])
        print("Migrating loyalty_points ...")
        migrate_loyalty_points(data, summaries["loyalty_points"])

        requests_in_json = len(data.get("requests", []))
        print(
            f"\nreservation_requests: {requests_in_json} found in data.json "
            "(this table was never persisted by the old app; nothing to migrate here)."
        )

        print("\nMigration summary:")
        for summary in summaries.values():
            print(summary.line())

        print(
            "\ndata.json has NOT been modified or deleted — it remains on disk as a "
            "legacy backup. The application no longer reads or writes it at runtime."
        )


if __name__ == "__main__":
    main()
