"""One-time migration of data.json into MySQL.

Usage (PowerShell, from the project root):
    python scripts\\migrate_json_to_mysql.py --dry-run
    python scripts\\migrate_json_to_mysql.py
    python scripts\\migrate_json_to_mysql.py --source data.json --report reports\\migration.json

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

--dry-run validates and stages inserts, then rolls back the whole unit of work.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
sys.path.insert(0, _SCRIPTS)

from flask import Flask  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from config import Config, ConfigError, TestConfig  # noqa: E402
from models import Booking, Feedback, LoyaltyPoint, Room, User, db  # noqa: E402
from seed_dev_users import ensure_seed_accounts  # noqa: E402

DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json"
)

ROOM_TYPES = {"Single", "Double", "Suite"}
ROOM_STATUSES = {"Available", "Booked", "Occupied", "Maintenance"}
BOOKING_STATUSES = {"Booked", "Checked In", "Checked Out", "Cancelled", "No-Show"}

# When False, migrate_* helpers flush only so --dry-run can roll back.
_ALLOW_COMMIT = True


def _commit():
    if _ALLOW_COMMIT:
        db.session.commit()
    else:
        db.session.flush()


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

    _commit()

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
        _commit()


def migrate_rooms(data, summary):
    """Insert missing rooms only. Match by id OR room_number (never duplicate)."""
    known_ids = {row[0] for row in db.session.execute(db.select(Room.id)).all()}
    known_numbers = {
        row[0] for row in db.session.execute(db.select(Room.room_number)).all()
    }
    source_rooms = data.get("rooms", [])
    print(f"Room source records read: {len(source_rooms)}")

    for record in source_rooms:
        room_id = record.get("id")
        if room_id is None:
            print("INVALID room record: missing id")
            summary.invalid += 1
            continue

        try:
            room_number = int(record.get("room_number"))
        except (TypeError, ValueError):
            print(f"INVALID room id={room_id}: room_number is not a valid integer")
            summary.invalid += 1
            continue

        if room_id in known_ids or room_number in known_numbers:
            summary.skipped_existing += 1
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
        known_numbers.add(room_number)
        summary.migrated += 1

    _commit()


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

    _commit()


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

    _commit()


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

    _commit()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Migrate legacy data.json into MySQL.")
    parser.add_argument("--source", default=DEFAULT_JSON_PATH, help="Path to data.json")
    parser.add_argument(
        "--database",
        choices=("normal", "test"),
        default="normal",
        help="normal → MYSQL_DATABASE; test → MYSQL_TEST_DATABASE",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and roll back")
    parser.add_argument("--verbose", action="store_true", help="Extra progress output")
    parser.add_argument("--report", default="", help="Write JSON report to this path")
    parser.add_argument(
        "--backup-dir",
        default="",
        help="Optional directory for a timestamped copy of the source JSON",
    )
    parser.add_argument(
        "--rooms-only",
        action="store_true",
        help=(
            "Insert missing rooms only (skip seed accounts, users, bookings, "
            "feedback, loyalty). Prefer this on EC2 when the DB already has users."
        ),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    started = datetime.now(timezone.utc).isoformat()
    source = os.path.abspath(args.source)

    try:
        app = Flask(__name__)
        app.config.from_object(TestConfig if args.database == "test" else Config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    db.init_app(app)

    global _ALLOW_COMMIT
    _ALLOW_COMMIT = not args.dry_run

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

        if not os.path.exists(source):
            print(f"No JSON found at {source} — nothing to migrate.")
            return

        source_hash = _sha256_file(source)
        if args.verbose:
            print(f"Source: {source}")
            print(f"SHA-256: {source_hash}")

        if args.backup_dir:
            os.makedirs(args.backup_dir, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = os.path.join(args.backup_dir, f"data.json.bak-{stamp}")
            shutil.copy2(source, backup_path)
            print(f"Backup copy written to {backup_path}")

        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)

        if args.rooms_only:
            if not args.dry_run:
                print("--rooms-only: skipping seed accounts and non-room tables.")
            summaries = {"rooms": Summary("rooms")}
            try:
                print("Migrating rooms ...")
                migrate_rooms(data, summaries["rooms"])
                if args.dry_run:
                    db.session.rollback()
                    print("\nDRY-RUN complete — all staged changes rolled back.")
            except Exception:
                db.session.rollback()
                raise
            requests_in_json = 0
        else:
            if not args.dry_run:
                print("Ensuring development seed accounts exist (admin/user/steph) ...")
                ensure_seed_accounts()
                print()
            elif args.verbose:
                print("Dry-run: skipping seed account writes.")

            summaries = {
                "users": Summary("users"),
                "rooms": Summary("rooms"),
                "bookings": Summary("bookings"),
                "feedback": Summary("feedback"),
                "loyalty_points": Summary("loyalty_points"),
            }

            try:
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

                if args.dry_run:
                    db.session.rollback()
                    print("\nDRY-RUN complete — all staged changes rolled back.")
            except Exception:
                db.session.rollback()
                raise

            requests_in_json = len(data.get("requests", []))
            print(
                f"\nreservation_requests: {requests_in_json} found in JSON "
                "(this table was never persisted by the old app; nothing to migrate here)."
            )

        print("\nMigration summary:")
        for summary in summaries.values():
            print(summary.line())

        report = {
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "source_sha256": source_hash,
            "database_mode": args.database,
            "dry_run": args.dry_run,
            "rooms_only": args.rooms_only,
            "counts": {
                name: {
                    "migrated": summary.migrated,
                    "skipped_existing": summary.skipped_existing,
                    "invalid": summary.invalid,
                }
                for name, summary in summaries.items()
            },
            "reservation_requests_in_json": requests_in_json,
            "data_json_modified": False,
        }
        if args.report:
            report_dir = os.path.dirname(os.path.abspath(args.report))
            if report_dir:
                os.makedirs(report_dir, exist_ok=True)
            with open(args.report, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
            print(f"\nReport written to {args.report}")

        print(
            "\ndata.json has NOT been modified or deleted — it remains on disk as a "
            "legacy backup. The application no longer reads or writes it at runtime."
        )


if __name__ == "__main__":
    main()
