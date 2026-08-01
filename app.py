import csv
import io
from datetime import datetime, timedelta
from urllib.parse import urlencode

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import repository as repo
from config import Config
from models import db
from repository import (
    ALLOWED_ROOM_STATUSES,
    ALLOWED_ROOM_TYPES,
    LOYALTY_POINTS_PER_DOLLAR,
    LOYALTY_POINTS_PER_NIGHT,
    LOYALTY_TIERS,
    MINIMUM_POINTS_REDEMPTION,
    POINTS_EXPIRY_DAYS,
    SINGAPORE_TZ,
    TIER_EARN_MULTIPLIER,
    _parse_booking_date,
    adjust_user_points,
    calculate_points_discount,
    cancel_user_request,
    checkin_booking,
    checkout_booking,
    create_booking,
    create_feedback,
    create_reservation_request,
    create_room,
    create_user,
    derive_room_details,
    expire_stale_points,
    feedback_exists_for_booking,
    filter_bookings,
    filter_rooms_by_type,
    get_booking,
    get_booking_length,
    get_existing_room_numbers,
    get_owned_feedback_by_id,
    get_room,
    get_sorted_feedback,
    get_tier_overview,
    get_user,
    get_user_booked_room_options,
    get_user_bookings,
    get_user_feedback_booking_options,
    get_user_lifetime_points,
    get_user_points_ledger,
    get_user_requests,
    get_user_submitted_feedback,
    get_user_tier,
    is_room_available,
    list_bookings,
    list_loyalty_adjustments,
    list_requests,
    list_rooms,
    list_users,
    mark_points_earned_seen,
    remove_past_bookings,
    set_room_status,
    set_user_last_seen_tier,
    update_booking_guest_details,
    update_room,
    update_user_password,
    username_exists,
)

MAX_FEEDBACK_LENGTH = 1000

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)


@app.route("/healthz")
def healthz():
    """Liveness/readiness probe for Compose, load balancers, and deploy smoke tests.

    WHY: Without a cheap, unauthenticated probe that also checks MySQL, a
    container can look "up" while every real request fails. Returning JSON
    plus 200/503 lets automation distinguish healthy from "process up, DB
    down" without scraping HTML or requiring a login session.
    """
    try:
        # Same SQLAlchemy text helper the test suite already uses in conftest.
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok", "database": "up"}), 200
    except Exception as exc:
        # Intentionally return only the exception class — never connection
        # strings, passwords, or hostnames that might appear in the message.
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "database": "down",
                    "detail": exc.__class__.__name__,
                }
            ),
            503,
        )


def verify_user_password(user, password):
    """Check a user dict's hashed password (MySQL always stores a hash, never plaintext)."""
    return check_password_hash(user["password_hash"], password)


def reset_user_password(username, new_password):
    """Reset a user's password and return success plus a message."""
    if not username or not new_password:
        return False, "Username and password are required"
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters long"
    if not username_exists(username):
        return False, "User not found"
    update_user_password(username, generate_password_hash(new_password))
    return True, "Password reset successfully."


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        reset_username = request.form.get("reset_username", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if reset_username:
            if not new_password or not confirm_password:
                return render_template("login.html", error="Please enter the new password and confirm it")
            if new_password != confirm_password:
                return render_template("login.html", error="Passwords do not match")
            success, message = reset_user_password(reset_username, new_password)
            return render_template("login.html", error=message if not success else None, success=message if success else None)

        if not username or not password:
            return render_template("login.html", error="Username and password are required")

        user = get_user(username)
        if user is not None and verify_user_password(user, password):
            session["username"] = username
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("user_dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password or not confirm_password:
            return render_template("register.html", error="All fields are required")

        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match")

        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters long")

        if any(u["username"].lower() == username.lower() for u in list_users()):
            return render_template("register.html", error="Username already exists")

        create_user(username, generate_password_hash(password), role="user")

        return render_template("register.html", success="Account created successfully! You can now log in.")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def admin_required():
    return session.get("role") == "admin"


def user_required():
    return session.get("role") == "user"


@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("login"))
    return render_template("admin_dashboard.html")


def get_next_stay_reminder(username, today=None):
    """Return a short reminder about the guest's nearest upcoming arrival or departure, or None."""
    if today is None:
        today = datetime.now(SINGAPORE_TZ).date()

    guest_bookings = get_user_bookings(username)

    for booking in guest_bookings:
        if booking.get("status") != "Checked In":
            continue
        checkout = _parse_booking_date(booking.get("checkout_date"))
        if not checkout:
            continue
        days = (checkout - today).days
        if days == 0:
            return f"Checkout today for Room {booking.get('room_number', 'N/A')} — don't forget to check out!"
        if days == 1:
            return f"Checkout is tomorrow for Room {booking.get('room_number', 'N/A')}."

    upcoming = [
        b for b in guest_bookings
        if (b.get("status") or "Booked") == "Booked" and _parse_booking_date(b.get("checkin_date"))
    ]
    upcoming.sort(key=lambda b: b.get("checkin_date") or "")
    for booking in upcoming:
        checkin = _parse_booking_date(booking.get("checkin_date"))
        days = (checkin - today).days
        if days == 0:
            return f"Your stay in Room {booking.get('room_number', 'N/A')} begins today!"
        if days == 1:
            return f"Your stay in Room {booking.get('room_number', 'N/A')} begins tomorrow."
        break

    return None


@app.route("/user/dashboard")
def user_dashboard():
    if not user_required():
        return redirect(url_for("login"))
    username = session.get("username")
    current_user = get_user(username)
    if expire_stale_points(username):
        current_user = get_user(username)
    points_balance = current_user.get("points", 0) if current_user else 0

    tier_name, tier_icon, points_to_next_tier, next_tier_name = get_user_tier(get_user_lifetime_points(username))
    stay_reminder = get_next_stay_reminder(username)

    tier_up_notification = None
    last_seen_tier = (current_user.get("last_seen_tier") if current_user else None) or LOYALTY_TIERS[0][0]
    if tier_name != last_seen_tier:
        tier_up_notification = {"tier_name": tier_name, "tier_icon": tier_icon}
        if current_user is not None:
            set_user_last_seen_tier(username, tier_name)

    unseen_earnings = [
        b for b in get_user_bookings(username)
        if b.get("points_awarded") and not b.get("points_earned_seen")
    ]
    points_earned_notification = None
    if unseen_earnings:
        points_earned_notification = sum(b.get("points_earned", 0) for b in unseen_earnings)
        mark_points_earned_seen([b["id"] for b in unseen_earnings])

    return render_template(
        "user_dashboard.html",
        points_balance=points_balance,
        tier_name=tier_name,
        tier_icon=tier_icon,
        points_to_next_tier=points_to_next_tier,
        next_tier_name=next_tier_name,
        points_earned_notification=points_earned_notification,
        stay_reminder=stay_reminder,
        tier_up_notification=tier_up_notification,
    )


@app.route("/loyalty/history")
def loyalty_history():
    if not user_required():
        return redirect(url_for("login"))
    username = session.get("username")
    current_user = get_user(username)
    if expire_stale_points(username):
        current_user = get_user(username)
    points_balance = current_user.get("points", 0) if current_user else 0
    ledger = get_user_points_ledger(username)
    tier_name, tier_icon, points_to_next_tier, next_tier_name = get_user_tier(get_user_lifetime_points(username))
    return render_template(
        "loyalty_history.html",
        points_balance=points_balance,
        ledger=ledger,
        tier_name=tier_name,
        tier_icon=tier_icon,
        points_to_next_tier=points_to_next_tier,
        next_tier_name=next_tier_name,
        tier_overview=get_tier_overview(),
        loyalty_points_per_dollar=LOYALTY_POINTS_PER_DOLLAR,
        minimum_points_redemption=MINIMUM_POINTS_REDEMPTION,
        points_expiry_days=POINTS_EXPIRY_DAYS,
    )


@app.route("/rooms")
def view_rooms():
    if "username" not in session:
        return redirect(url_for("login"))

    selected_type = request.args.get("room_type", "").strip()
    room_list = list_rooms()
    filtered_rooms = filter_rooms_by_type(room_list, selected_type)
    if session.get("role") != "admin":
        filtered_rooms = [room for room in filtered_rooms if room.get("status") == "Available"]
    return render_template(
        "rooms.html",
        rooms=filtered_rooms,
        selected_room_type=selected_type,
        loyalty_points_per_night=LOYALTY_POINTS_PER_NIGHT,
    )


@app.route("/admin/rooms/add", methods=["GET", "POST"])
def add_room():
    if not admin_required():
        return redirect(url_for("login"))

    existing_numbers = get_existing_room_numbers()
    entered_room_number = ""
    entered_status = "Available"

    if request.method == "POST":
        entered_room_number = request.form.get("room_number", "").strip()
        entered_status = request.form.get("status", "Available").strip()
        details = derive_room_details(entered_room_number)

        template_context = {
            "existing_room_numbers": existing_numbers,
            "entered_room_number": entered_room_number,
            "entered_status": entered_status,
        }

        if details is None:
            return render_template(
                "add_room.html",
                error="Room number must be a whole number from 1 to 50.",
                **template_context,
            )

        room_number = details["room_number"]
        template_context["entered_room_number"] = room_number
        if details["number"] in existing_numbers:
            return render_template(
                "add_room.html",
                error=f"Room {room_number} already exists. Please choose another room number.",
                **template_context,
            )

        if entered_status not in ALLOWED_ROOM_STATUSES:
            return render_template(
                "add_room.html",
                error="Please select Available, Booked or Maintenance.",
                **template_context,
            )

        create_room(entered_room_number, entered_status)

        return redirect(url_for("view_rooms"))

    return render_template(
        "add_room.html",
        existing_room_numbers=existing_numbers,
        entered_room_number=entered_room_number,
        entered_status=entered_status,
    )


@app.route("/admin/rooms/edit/<int:room_id>", methods=["GET", "POST"])
def edit_room(room_id):
    if not admin_required():
        return redirect(url_for("login"))

    room = get_room(room_id)
    if room is None:
        return "Room not found", 404

    existing_numbers = get_existing_room_numbers(exclude_room_id=room_id)

    if request.method == "POST":
        entered_room_number = request.form.get("room_number", "").strip()
        details = derive_room_details(entered_room_number)
        status = request.form.get("status", "").strip()

        if details is None:
            return render_template(
                "edit_room.html",
                room=room,
                error="Room number must be a whole number from 1 to 50.",
                existing_room_numbers=existing_numbers,
            )

        if details["number"] in existing_numbers:
            return render_template(
                "edit_room.html",
                room=room,
                error=f"Room {details['room_number']} already exists. Please choose another room number.",
                existing_room_numbers=existing_numbers,
            )

        if status not in ALLOWED_ROOM_STATUSES:
            return render_template(
                "edit_room.html",
                room=room,
                error="Please select Available, Booked or Maintenance.",
                existing_room_numbers=existing_numbers,
            )

        update_room(room_id, entered_room_number, status)

        return redirect(url_for("view_rooms"))

    return render_template(
        "edit_room.html",
        room=room,
        existing_room_numbers=existing_numbers,
    )


@app.route("/admin/rooms/delete/<int:room_id>")
def delete_room(room_id):
    if not admin_required():
        return redirect(url_for("login"))

    repo.delete_room(room_id)

    return redirect(url_for("view_rooms"))


@app.route("/admin/rooms/status/<int:room_id>", methods=["POST"])
def update_room_status(room_id):
    """Update a room's status inline (used by the room-availability status filter)."""
    if not admin_required():
        return jsonify({"error": "Unauthorized"}), 403

    room = get_room(room_id)
    if room is None:
        return jsonify({"error": "Room not found"}), 404

    status = request.form.get("status", "").strip()
    if status not in ALLOWED_ROOM_STATUSES:
        return jsonify({"error": "Please select Available, Booked or Maintenance."}), 400

    updated = set_room_status(room_id, status)

    return jsonify({"id": room_id, "status": updated["status"]})


@app.route("/book/<int:room_id>", methods=["GET", "POST"])
def book_room(room_id):
    if not user_required():
        return redirect(url_for("login"))

    room = get_room(room_id)
    if room is None:
        return "Room not found", 404

    username = session.get("username")
    current_user = get_user(username)
    if expire_stale_points(username):
        current_user = get_user(username)
    points_balance = current_user.get("points", 0) if current_user else 0

    if request.method == "GET":
        tier_name, tier_icon, _, _ = get_user_tier(get_user_lifetime_points(username))
        return render_template(
            "book_room.html",
            room=room,
            points_balance=points_balance,
            loyalty_points_per_dollar=LOYALTY_POINTS_PER_DOLLAR,
            loyalty_points_per_night=LOYALTY_POINTS_PER_NIGHT.get(room.get("type"), 0),
            minimum_points_redemption=MINIMUM_POINTS_REDEMPTION,
            tier_name=tier_name,
            tier_icon=tier_icon,
            tier_earn_multiplier=TIER_EARN_MULTIPLIER.get(tier_name, 1.0),
        )

    checkin = request.form.get("checkin_date")
    checkout = request.form.get("checkout_date")
    guest_first_name = request.form.get("guest_first_name", "").strip()
    guest_last_name = request.form.get("guest_last_name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    email = request.form.get("email", "").strip()
    if not checkin or not checkout:
        return render_template("book_room.html", room=room, error="Please provide both check-in and check-out dates.")

    if not guest_first_name or not guest_last_name:
        return render_template("book_room.html", room=room, error="Please provide guest first and last name.")

    if not phone_number or not email:
        return render_template("book_room.html", room=room, error="Please provide phone number and email.")

    if not is_valid_phone_number(phone_number):
        return render_template(
            "book_room.html",
            room=room,
            error="Phone number must be exactly 8 digits and start with 8 or 9.",
        )

    try:
        checkin_date = datetime.strptime(checkin, "%Y-%m-%d").date()
        checkout_date = datetime.strptime(checkout, "%Y-%m-%d").date()
    except ValueError:
        return render_template("book_room.html", room=room, error="Invalid date format.")

    if checkin_date >= checkout_date:
        return render_template("book_room.html", room=room, error="Check-out must be after check-in.")

    if not is_room_available(room_id, checkin, checkout):
        return render_template(
            "book_room.html",
            room=room,
            error="This room is already booked for the selected dates. Please choose different dates.",
        )

    nights = get_booking_length(checkin, checkout)
    room_total = room.get("price", 0) * nights

    try:
        points_requested = int(request.form.get("points_redeemed", "0") or 0)
    except ValueError:
        points_requested = 0
    points_requested = max(0, min(points_requested, points_balance))
    if points_requested < MINIMUM_POINTS_REDEMPTION:
        points_requested = 0
    points_used, points_discount = calculate_points_discount(points_requested, room_total)

    create_booking(
        room_id=room.get("id"),
        room_number=room.get("room_number"),
        room_type=room.get("type"),
        price=room.get("price"),
        checkin_date=checkin_date.strftime("%Y-%m-%d"),
        checkout_date=checkout_date.strftime("%Y-%m-%d"),
        username=session.get("username"),
        guest_first_name=guest_first_name,
        guest_last_name=guest_last_name,
        phone_number=phone_number,
        email=email,
        points_redeemed=points_used,
        points_discount=points_discount,
        total_price=round(room_total - points_discount, 2),
    )

    return redirect(url_for("view_bookings"))


@app.route("/bookings")
def view_bookings():
    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        data = get_user_bookings(session.get("username"))
        booked_bookings = [b for b in data if (b.get("status") or "Booked") == "Booked"]
        checkedin_bookings = [b for b in data if b.get("status") == "Checked In"]
        checkedout_bookings = [b for b in data if b.get("status") == "Checked Out"]
        cancelled_bookings = [b for b in data if b.get("status") in ("Cancelled", "No-Show")]
        return render_template(
            "bookings.html",
            bookings=data,
            booked_bookings=booked_bookings,
            checkedin_bookings=checkedin_bookings,
            checkedout_bookings=checkedout_bookings,
            cancelled_bookings=cancelled_bookings,
        )

    all_bookings = list_bookings()
    stats = build_checkin_dashboard_data(all_bookings, role="admin")

    message = request.args.get("message")
    search = request.args.get("search", "")
    status_filter = request.args.get("status", "")
    room_type_filter = request.args.get("room_type", "")
    checkin_filter = request.args.get("checkin_date", "")
    checkout_filter = request.args.get("checkout_date", "")
    view_archived = request.args.get("view") == "archived"

    filtered = filter_bookings(
        all_bookings,
        search=search,
        status=status_filter,
        room_type=room_type_filter,
        checkin_date=checkin_filter,
        checkout_date=checkout_filter,
        archived=view_archived,
    )
    filtered = sorted(filtered, key=lambda b: b.get("id", 0))

    user_points_map = {u.get("username"): u.get("points", 0) for u in list_users()}
    for booking in filtered:
        booking["status_badge"] = get_booking_status_badge(booking.get("status"))
        booking["nights"] = get_booking_length(booking.get("checkin_date"), booking.get("checkout_date"))
        booking["guest_points_balance"] = user_points_map.get(booking.get("username"), 0)

    page_items, total_pages, page = paginate_list(filtered, page=request.args.get("page", "1"), per_page=10)

    base_query = urlencode({
        key: value for key, value in {
            "search": search,
            "status": status_filter,
            "room_type": room_type_filter,
            "checkin_date": checkin_filter,
            "checkout_date": checkout_filter,
            "view": "archived" if view_archived else "",
        }.items() if value
    })

    return render_template(
        "bookings.html",
        bookings=page_items,
        stats=stats,
        room_types=ALLOWED_ROOM_TYPES,
        message=message,
        search=search,
        status_filter=status_filter,
        room_type_filter=room_type_filter,
        checkin_filter=checkin_filter,
        checkout_filter=checkout_filter,
        page=page,
        total_pages=total_pages,
        total_matching=len(filtered),
        base_query=base_query,
        view_archived=view_archived,
        archived_count=sum(1 for b in all_bookings if b.get("archived")),
    )


@app.route("/bookings/export")
def export_bookings_csv():
    """Export the admin's currently filtered bookings (all matching pages) as CSV."""
    if not admin_required():
        return redirect(url_for("login"))

    filtered = filter_bookings(
        list_bookings(),
        search=request.args.get("search", ""),
        status=request.args.get("status", ""),
        room_type=request.args.get("room_type", ""),
        checkin_date=request.args.get("checkin_date", ""),
        checkout_date=request.args.get("checkout_date", ""),
        archived=request.args.get("view") == "archived",
    )
    filtered = sorted(filtered, key=lambda b: b.get("id", 0))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Booking ID", "Guest Name", "Room Number", "Room Type",
        "Check-In Date", "Check-Out Date", "Phone", "Email", "Status", "Booked By",
    ])
    for booking in filtered:
        writer.writerow([
            booking.get("id", ""),
            booking.get("guest_name", ""),
            booking.get("room_number", ""),
            booking.get("room_type", ""),
            booking.get("checkin_date", ""),
            booking.get("checkout_date", ""),
            booking.get("phone_number", ""),
            booking.get("email", ""),
            booking.get("status") or "Booked",
            booking.get("username", ""),
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=bookings_export.csv"},
    )


@app.route("/admin/points/adjust", methods=["POST"])
def adjust_points_route():
    if not admin_required():
        return redirect(url_for("login"))

    username = request.form.get("username", "").strip()
    reason = request.form.get("reason", "").strip()

    try:
        points = int(request.form.get("points", "0") or 0)
    except ValueError:
        points = 0

    if username and reason and points != 0:
        adjust_user_points(username, points, reason, session.get("username"))
        message = f"{'+' if points > 0 else ''}{points} points applied to {username}."
        return redirect(url_for("view_bookings", message=message))

    return redirect(url_for("view_bookings"))


@app.route("/admin/points/adjustments")
def admin_points_log():
    """Admin-wide audit log of every manual point adjustment ever made."""
    if not admin_required():
        return redirect(url_for("login"))

    entries = sorted(list_loyalty_adjustments(), key=lambda a: a.get("created_at") or "", reverse=True)
    for entry in entries:
        entry["display_date"] = format_submission_timestamp(entry.get("created_at")) or "N/A"

    total_outstanding_points = sum(u.get("points", 0) for u in list_users())

    return render_template(
        "admin_points_log.html",
        adjustments=entries,
        total_adjustments=len(entries),
        total_outstanding_points=total_outstanding_points,
        total_outstanding_value=round(total_outstanding_points / LOYALTY_POINTS_PER_DOLLAR, 2),
    )


ARCHIVABLE_BOOKING_STATUSES = repo.ARCHIVABLE_BOOKING_STATUSES


@app.route("/admin/bookings/archive/<int:booking_id>")
def archive_booking(booking_id):
    """Hide a finished booking from the main admin view without deleting it."""
    if not admin_required():
        return redirect(url_for("login"))

    repo.archive_booking(booking_id, archived=True)

    return redirect(url_for("view_bookings"))


@app.route("/admin/bookings/unarchive/<int:booking_id>")
def unarchive_booking(booking_id):
    if not admin_required():
        return redirect(url_for("login"))

    repo.archive_booking(booking_id, archived=False)

    return redirect(url_for("view_bookings", view="archived"))


@app.route("/admin/bookings/edit/<int:booking_id>", methods=["GET", "POST"])
def edit_booking(booking_id):
    """Let admin correct a booking's guest contact details and stay dates."""
    if not admin_required():
        return redirect(url_for("login"))

    booking = get_booking(booking_id)
    if booking is None:
        return "Booking not found", 404

    if (booking.get("status") or "Booked") != "Checked In":
        return redirect(url_for("view_bookings"))

    if request.method == "POST":
        guest_first_name = request.form.get("guest_first_name", "").strip()
        guest_last_name = request.form.get("guest_last_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        email = request.form.get("email", "").strip()
        checkin_date = request.form.get("checkin_date", "").strip()
        checkout_date = request.form.get("checkout_date", "").strip()

        error = None
        if not guest_first_name or not guest_last_name:
            error = "Please provide guest first and last name."
        elif not phone_number or not email:
            error = "Please provide phone number and email."
        elif not is_valid_phone_number(phone_number):
            error = "Phone number must be exactly 8 digits and start with 8 or 9."
        else:
            try:
                checkin_parsed = datetime.strptime(checkin_date, "%Y-%m-%d").date()
                checkout_parsed = datetime.strptime(checkout_date, "%Y-%m-%d").date()
            except ValueError:
                error = "Invalid date format."
            else:
                if checkin_parsed >= checkout_parsed:
                    error = "Check-out must be after check-in."
                elif not is_room_available(booking.get("room_id"), checkin_date, checkout_date, exclude_booking_id=booking_id):
                    error = "This room is already booked for the selected dates. Please choose different dates."

        if error:
            return render_template("edit_booking.html", booking=booking, error=error)

        update_booking_guest_details(
            booking_id, guest_first_name, guest_last_name, phone_number, email, checkin_date, checkout_date
        )

        return redirect(url_for("view_bookings"))

    return render_template("edit_booking.html", booking=booking, error=None)


@app.route("/bookings/remove-past")
def remove_past_bookings_route():
    if "username" not in session:
        return redirect(url_for("login"))
    if not admin_required():
        return redirect(url_for("view_bookings"))

    remove_past_bookings()
    return redirect(url_for("view_bookings"))


def get_booking_status_badge(status):
    """Return a display label and CSS class for a booking status."""
    normalized = (status or "Booked").strip().lower()
    status_map = {
        "checked in": {"label": "Checked In", "class": "status-badge status-checkedin"},
        "checked out": {"label": "Checked Out", "class": "status-badge status-checkedout"},
        "booked": {"label": "Booked", "class": "status-badge status-booked"},
        "cancelled": {"label": "Cancelled", "class": "status-badge status-cancelled"},
        "no-show": {"label": "No-Show", "class": "status-badge status-cancelled"},
        "pending": {"label": "Pending", "class": "status-badge status-pending"},
    }
    return status_map.get(normalized, status_map["booked"])


def get_booking_days_until(checkin_date, today=None):
    """Return how many days remain until a booking check-in date."""
    if today is None:
        today = datetime.now().date()
    checkin = _parse_booking_date(checkin_date)
    if not checkin:
        return None
    return (checkin - today).days


def build_checkin_dashboard_data(bookings, role="admin", today=None):
    """Create summary metrics and a highlight booking for the check-in page."""
    if today is None:
        today = datetime.now().date()

    today_str = today.strftime("%Y-%m-%d")
    total_bookings = len(bookings)
    checked_in_count = sum(1 for booking in bookings if (booking.get("status") or "Booked") == "Checked In")
    pending_count = sum(1 for booking in bookings if (booking.get("status") or "Booked") in {"Booked", "Pending"})
    checked_out_count = sum(1 for booking in bookings if (booking.get("status") or "Booked") == "Checked Out")

    arrivals_today = sum(
        1
        for booking in bookings
        if (booking.get("checkin_date") or "") == today_str and (booking.get("status") or "Booked") in {"Booked", "Checked In"}
    )
    departures_today = sum(
        1
        for booking in bookings
        if (booking.get("checkout_date") or "") == today_str and (booking.get("status") or "Booked") in {"Booked", "Checked In"}
    )
    occupancy_rate = int(round((checked_in_count / total_bookings) * 100)) if total_bookings else 0

    upcoming_bookings = [
        booking
        for booking in bookings
        if (booking.get("status") or "Booked") in {"Booked", "Checked In"}
    ]
    upcoming_bookings.sort(key=lambda booking: booking.get("checkin_date") or "")

    next_booking = None
    if upcoming_bookings:
        next_booking = upcoming_bookings[0]

    return {
        "total_bookings": total_bookings,
        "checked_in_count": checked_in_count,
        "pending_count": pending_count,
        "checked_out_count": checked_out_count,
        "arrivals_today": arrivals_today,
        "departures_today": departures_today,
        "occupancy_rate": occupancy_rate,
        "next_booking": next_booking,
        "role": role,
    }


def paginate_list(items, page=1, per_page=10):
    """Return (page_items, total_pages, current_page); current_page is clamped into range."""
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = min(max(1, page), total_pages)
    start = (page - 1) * per_page
    return items[start:start + per_page], total_pages, page


CATEGORY_BASE_PRIORITY = {
    "Repair": "High",
    "Food & Beverage": "Medium",
    "Toiletries": "Low",
    "Other": "Low",
}

URGENT_PRIORITY_KEYWORDS = [
    "leak", "flood", "flooding", "no power", "no electricity", "power outage",
    "gas smell", "smoke", "fire", "locked out", "lock broken", "broken lock",
    "can't lock", "cannot lock", "no ac", "no aircon", "no air conditioning",
    "no heater", "no heating", "security", "break-in", "emergency", "urgent",
]

PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
PRIORITY_ESCALATION_MINUTES = {"Low": 30, "Medium": 20}


def determine_request_priority(request_type, message):
    """Auto-assign a request's base priority from its category, escalated by urgency keywords."""
    message_lower = (message or "").lower()
    if any(keyword in message_lower for keyword in URGENT_PRIORITY_KEYWORDS):
        return "High"
    return CATEGORY_BASE_PRIORITY.get(request_type, "Low")


def _minutes_since(timestamp_iso, now=None):
    """Whole minutes elapsed since an ISO timestamp; 0 if missing or unparsable."""
    if not timestamp_iso:
        return 0
    try:
        created = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return 0
    if now is None:
        now = datetime.now(SINGAPORE_TZ)
    if created.tzinfo is None:
        created = created.replace(tzinfo=SINGAPORE_TZ)
    return max(0, int((now - created).total_seconds() // 60))


def get_effective_priority(request_entry, now=None):
    """Return (label, escalated) after applying wait-time escalation to a request's base priority."""
    base_priority = request_entry.get("priority", "Low")
    if base_priority == "High":
        return base_priority, False

    elapsed = _minutes_since(request_entry.get("created_at"), now)
    low_to_medium = PRIORITY_ESCALATION_MINUTES["Low"]
    medium_to_high = PRIORITY_ESCALATION_MINUTES["Medium"]

    if base_priority == "Low":
        if elapsed >= low_to_medium + medium_to_high:
            return "High", True
        if elapsed >= low_to_medium:
            return "Medium", True
        return "Low", False

    if base_priority == "Medium":
        if elapsed >= medium_to_high:
            return "High", True
        return "Medium", False

    return base_priority, False


def _room_type_priority_rank(room_type):
    """Suite < Double < Single, used only to break ties between equal request priorities."""
    room_type_lower = (room_type or "").lower()
    if "suite" in room_type_lower:
        return 0
    if "double" in room_type_lower:
        return 1
    return 2


def get_priority_score(request_entry, now=None):
    """Numeric priority score for sorting/display; lower means more urgent."""
    effective_priority, _ = get_effective_priority(request_entry, now)
    room_bonus = 2 - _room_type_priority_rank(request_entry.get("room_type"))
    waiting_minutes = _minutes_since(request_entry.get("created_at"), now)
    return PRIORITY_RANK.get(effective_priority, 2) * 1000 - room_bonus * 10 - waiting_minutes


def _format_clock_time(dt):
    """Human-readable clock time (e.g. '2:30 PM') for a datetime."""
    return dt.strftime("%I:%M %p").lstrip("0")


def get_expected_arrival_display(req):
    """Clock time the request is expected to arrive by, using the minimum estimate."""
    timestamp_iso = req.get("created_at")
    estimated_min = req.get("estimated_min")
    if not timestamp_iso or estimated_min is None:
        return None
    try:
        created = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=SINGAPORE_TZ)
    return _format_clock_time(created + timedelta(minutes=estimated_min))


def format_submission_timestamp(timestamp_iso):
    """Human-readable submission date and time in Singapore time, e.g. 'Jul 29, 2026, 4:41 PM'."""
    if not timestamp_iso:
        return None
    try:
        created = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=SINGAPORE_TZ)
    return created.strftime("%b %d, %Y, ") + _format_clock_time(created)


def format_ledger_timestamp(timestamp_iso):
    """Human-readable date and time for a loyalty ledger row, e.g. 'July 29, 2026, 4:41 PM'."""
    if not timestamp_iso:
        return None
    try:
        created = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=SINGAPORE_TZ)
    return created.strftime("%B %d, %Y, ") + _format_clock_time(created)


def get_display_status(req):
    """User-facing status: Pending, Completed, or Cancelled."""
    status = req.get("status")
    if status == "Accepted":
        return "Completed"
    return status or "Pending"


def get_remaining_estimate_display(req, now=None):
    """Human-readable time remaining until the request's estimated completion."""
    min_mins = req.get("estimated_min")
    max_mins = req.get("estimated_max")
    if min_mins is None or max_mins is None:
        return req.get("estimated_time")

    elapsed = _minutes_since(req.get("created_at"), now)
    remaining_min = max(0, min_mins - elapsed)
    remaining_max = max_mins - elapsed

    if remaining_max <= 0:
        return "Any moment now"
    if remaining_min == 0:
        return f"Up to {remaining_max} minutes remaining"
    return f"{remaining_min}-{remaining_max} minutes remaining"


def annotate_request_for_display(req, now=None):
    """Return a copy of a request enriched with computed display fields."""
    view = dict(req)
    effective_priority, escalated = get_effective_priority(req, now)

    view["effective_priority"] = effective_priority
    view["escalated"] = escalated
    view["waiting_minutes"] = _minutes_since(req.get("created_at"), now)
    view["expected_arrival"] = get_expected_arrival_display(req)
    view["estimated_time_remaining"] = get_remaining_estimate_display(req, now)
    view["priority_score"] = get_priority_score(req, now)
    view["display_status"] = get_display_status(req)
    return view


TOILETRY_FIELDS = [
    ("Toothbrush", "toiletry_toothbrush"),
    ("Toothpaste", "toiletry_toothpaste"),
    ("Shampoo", "toiletry_shampoo"),
    ("Conditioner", "toiletry_conditioner"),
    ("Soap", "toiletry_soap"),
    ("Body Wash", "toiletry_bodywash"),
    ("Razor", "toiletry_razor"),
    ("Shaving Cream", "toiletry_shavingcream"),
    ("Cotton Buds", "toiletry_cottonbuds"),
    ("Comb", "toiletry_comb"),
    ("Shower Cap", "toiletry_showercap"),
    ("Body Lotion", "toiletry_bodylotion"),
    ("Deodorant", "toiletry_deodorant"),
    ("Mouthwash", "toiletry_mouthwash"),
    ("Bathrobe", "toiletry_bathrobe"),
    ("Slippers", "toiletry_slippers"),
]


def validate_request_form(form_data):
    """Validate request form inputs and return an error string or None."""
    request_type = str(form_data.get("request_type", "") or "").strip()
    if request_type != "Toiletries":
        return None

    for _, field_name in TOILETRY_FIELDS:
        raw_value = str(form_data.get(field_name, "0") or "0").strip()
        try:
            quantity = int(raw_value)
        except ValueError:
            continue
        if quantity == 0:
            continue
        if quantity < 1 or quantity > 5:
            return "Please enter the correct quantity which is 1-5."
    return None


def build_request_message(form_data):
    """Convert form selections into a structured request message."""
    request_type = str(form_data.get("request_type", "") or "").strip()

    if request_type == "Toiletries":
        selected_items = []
        for label, field_name in TOILETRY_FIELDS:
            try:
                quantity = int(str(form_data.get(field_name, "0") or "0").strip())
            except ValueError:
                quantity = 0
            quantity = max(0, min(5, quantity))
            if quantity > 0:
                selected_items.append(f"{label} x{quantity}")
        return f"Toiletries: {'; '.join(selected_items)}" if selected_items else ""

    if request_type == "Food & Beverage":
        selections = []
        food_item = str(form_data.get("food_item", "") or "").strip()
        drink = str(form_data.get("drink", "") or "").strip()
        soup = str(form_data.get("soup", "") or "").strip()
        dessert = str(form_data.get("dessert", "") or "").strip()
        if food_item:
            selections.append(f"Meal: {food_item}")
        if drink:
            selections.append(f"Drink: {drink}")
        if soup:
            selections.append(f"Soup: {soup}")
        if dessert:
            selections.append(f"Dessert: {dessert}")
        return f"Food & Beverage: {'; '.join(selections)}" if selections else ""

    if request_type == "Repair":
        equipment = str(form_data.get("repair_equipment", "") or "").strip()
        issue = str(form_data.get("repair_issue", "") or "").strip()
        details = []
        if equipment:
            details.append(f"Equipment: {equipment}")
        if issue:
            details.append(f"Issue: {issue}")
        return f"Repair: {'; '.join(details)}" if details else ""

    other_details = str(form_data.get("other_request_text", "") or "").strip()
    return f"Other request: {other_details}" if other_details else ""


def is_valid_phone_number(phone_number):
    """Return True when a phone number is exactly 8 digits and starts with 8 or 9."""
    cleaned = str(phone_number or "").strip()
    return len(cleaned) == 8 and cleaned.isdigit() and cleaned.startswith(("8", "9"))


def _estimate_minutes_range(message, current_time=None):
    """Return (min_mins, max_mins, peak_desc) for a request's category at the given time."""
    if current_time is None:
        current_time = datetime.now(SINGAPORE_TZ)

    message_lower = message.lower()
    hour = current_time.hour
    is_peak = 11 <= hour <= 15 or 18 <= hour <= 22
    peak_desc = "peak hours" if is_peak else "non-peak hours"

    def pick_range(non_peak_range, peak_range):
        return peak_range if is_peak else non_peak_range

    if 'toiletries' in message_lower:
        min_mins, max_mins = pick_range((5, 10), (10, 15))
    elif any(word in message_lower for word in ['food & beverage', 'food', 'drink', 'room service', 'meal', 'coffee', 'tea', 'snack', 'beverage', 'breakfast', 'lunch', 'dinner', 'order', 'delivery', 'pizza', 'burger', 'water', 'juice', 'soda', 'restaurant', 'hungry', 'thirsty', 'eat', 'refresh']):
        min_mins, max_mins = pick_range((15, 25), (30, 40))
    elif any(word in message_lower for word in ['repair', 'fix', 'broken', 'maintenance', 'ac', 'heater', 'light', 'lock', 'door', 'issue', 'problem', 'damaged', 'leak', 'plumbing', 'electric', 'tv', 'wifi', 'internet', 'bulb', 'switch', 'handle', 'knob', 'toilet', 'sink', 'faucet', 'drain', 'cable']):
        min_mins, max_mins = pick_range((60, 120), (90, 180))
    else:
        min_mins, max_mins = pick_range((15, 30), (25, 45))

    return min_mins, max_mins, peak_desc


def estimate_request_time(message, current_time=None):
    """Estimate completion time from request category and hotel peak hours only.

    Priority no longer changes how long a task physically takes to fulfil —
    a Suite guest's meal doesn't cook any faster than a Single guest's.
    Priority still affects queue ORDER (see sort_requests_by_priority), just
    not this duration estimate.
    """
    min_mins, max_mins, peak_desc = _estimate_minutes_range(message, current_time)
    return f"{min_mins}-{max_mins} minutes ({peak_desc})"


def _pick_by_room_type(candidates):
    """Among equally-ranked candidates, prefer the higher room grade; remaining ties keep arrival order."""
    candidates = list(candidates)
    best_room_rank = min(_room_type_priority_rank(req.get("room_type")) for req in candidates)
    return next(req for req in candidates if _room_type_priority_rank(req.get("room_type")) == best_room_rank)


def sort_requests_by_priority(requests, now=None):
    """Order pending requests into admin's recommended handling queue."""
    now = now or datetime.now(SINGAPORE_TZ)

    def effective(req):
        return get_effective_priority(req, now)[0]

    pending = [req for req in requests if req.get("status") == "Pending"]
    others = [req for req in requests if req.get("status") != "Pending"]

    remaining = list(pending)
    served = []
    batch_size = 0
    batch_served_medium = False
    batch_served_low = False

    while remaining:
        if batch_size == 3 and not batch_served_medium and any(effective(req) == "Medium" for req in remaining):
            chosen = _pick_by_room_type(req for req in remaining if effective(req) == "Medium")
        elif batch_size == 4 and not batch_served_low and any(effective(req) == "Low" for req in remaining):
            chosen = _pick_by_room_type(req for req in remaining if effective(req) == "Low")
        else:
            best_rank = min(PRIORITY_RANK.get(effective(req), 2) for req in remaining)
            chosen = _pick_by_room_type(
                req for req in remaining if PRIORITY_RANK.get(effective(req), 2) == best_rank
            )

        served.append(chosen)
        remaining.remove(chosen)

        chosen_effective = effective(chosen)
        if chosen_effective == "Medium":
            batch_served_medium = True
        elif chosen_effective == "Low":
            batch_served_low = True

        batch_size += 1
        if batch_size == 5:
            batch_size = 0
            batch_served_medium = False
            batch_served_low = False

    return served + others


def parse_request_line_items(message):
    """Split a stored request message into itemised lines for the receipt."""
    if not message:
        return []
    _, separator, remainder = message.partition(": ")
    if not separator:
        return [message]
    return [item.strip() for item in remainder.split("; ") if item.strip()]


@app.route("/requests", methods=["GET", "POST"])
def user_requests():
    if "username" not in session:
        return redirect(url_for("login"))

    error = None

    if request.method == "POST" and session["role"] == "user":
        request_type = request.form.get("request_type", "").strip()
        message = build_request_message(request.form.to_dict())
        room_number = request.form.get("room_number", "").strip()

        checked_in_booking = next(
            (
                booking for booking in get_user_bookings(session.get("username"))
                if booking.get("room_number") == room_number
                and booking.get("status") == "Checked In"
            ),
            None
        )

        if not checked_in_booking:
            error = "You can only submit a special request after the admin has checked you in."
        elif not request_type:
            error = "Please choose a request category."
        else:
            validation_error = validate_request_form(request.form.to_dict())
            if validation_error:
                error = validation_error
            elif not message:
                if request_type == "Toiletries":
                    error = "Please choose at least one toiletry item and quantity."
                elif request_type == "Food & Beverage":
                    error = "Please choose at least one item from the food and beverage menu."
                elif request_type == "Repair":
                    error = "Please choose the equipment and describe the repair issue."
                else:
                    error = "Please describe your other request."
            else:
                room_type = checked_in_booking.get("room_type", "")
                guest_name = checked_in_booking.get("guest_name") or session["username"]
                priority = determine_request_priority(request_type, message)
                estimated_min, estimated_max, estimated_peak_desc = _estimate_minutes_range(message)
                estimated_time = f"{estimated_min}-{estimated_max} minutes ({estimated_peak_desc})"

                new_request = create_reservation_request(
                    username=session["username"],
                    room_number=room_number,
                    room_type=room_type,
                    category=request_type,
                    message=message,
                    guest_name=guest_name,
                    priority=priority,
                    estimated_min=estimated_min,
                    estimated_max=estimated_max,
                    estimated_time=estimated_time,
                )

                return redirect(url_for("user_requests", ticket=new_request["id"]))

    filter_status = request.args.get("filter_status", "")
    filter_priority = request.args.get("filter_priority", "")
    filter_category = request.args.get("filter_category", "")
    sort_by = request.args.get("sort", "priority")

    if session.get("role") == "admin":
        now = datetime.now(SINGAPORE_TZ)
        ordered = sort_requests_by_priority(list_requests(), now=now)
        data = [annotate_request_for_display(r, now) for r in ordered]

        queue_position = 1
        for r in data:
            if r.get("status") == "Pending":
                r["queue_position"] = queue_position
                queue_position += 1

        has_any_requests = bool(data)

        if filter_status:
            data = [r for r in data if r.get("display_status") == filter_status]
        if filter_priority:
            data = [r for r in data if r["effective_priority"] == filter_priority]
        if filter_category:
            data = [r for r in data if r.get("category") == filter_category]

        if sort_by == "waiting":
            data = sorted(data, key=lambda r: -r["waiting_minutes"])
        elif sort_by == "room":
            data = sorted(data, key=lambda r: str(r.get("room_number", "")))
    else:
        data = [annotate_request_for_display(r) for r in get_user_requests(session.get("username"))]
        has_any_requests = bool(data)

    receipt_request = None
    if session.get("role") == "user":
        ticket_param = request.args.get("ticket", "").strip()
        if ticket_param:
            try:
                ticket_request_id = int(ticket_param)
            except ValueError:
                ticket_request_id = None
            if ticket_request_id is not None:
                matched_request = next(
                    (r for r in get_user_requests(session.get("username")) if r.get("id") == ticket_request_id),
                    None,
                )
                if matched_request is not None:
                    receipt_request = annotate_request_for_display(matched_request)
                    receipt_request["line_items"] = parse_request_line_items(receipt_request.get("message", ""))
                    receipt_request["submitted_at_display"] = format_submission_timestamp(receipt_request.get("created_at"))

    room_options = get_user_booked_room_options(session["username"]) if session.get("role") == "user" else []
    return render_template(
        "requests.html",
        requests_list=data,
        room_options=room_options,
        error=error,
        filter_status=filter_status,
        filter_priority=filter_priority,
        filter_category=filter_category,
        sort_by=sort_by,
        receipt_request=receipt_request,
        has_any_requests=has_any_requests,
    )


@app.route("/admin/requests/accept/<int:request_id>")
def accept_request(request_id):
    if not admin_required():
        return redirect(url_for("login"))

    repo.accept_request(request_id, _estimate_minutes_range)

    return redirect(url_for("user_requests"))


@app.route("/admin/requests/accept-all")
def accept_all_requests():
    if not admin_required():
        return redirect(url_for("login"))

    repo.accept_all_requests(_estimate_minutes_range)
    return redirect(url_for("user_requests"))


@app.route("/requests/cancel/<int:request_id>")
def cancel_request(request_id):
    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "user":
        return redirect(url_for("user_requests"))

    cancel_user_request(request_id, session.get("username"))
    return redirect(url_for("user_requests"))


@app.route("/requests/received/<int:request_id>")
def mark_request_received(request_id):
    if "username" not in session:
        return redirect(url_for("login"))

    repo.mark_request_received(request_id, session.get("username"))

    return redirect(url_for("user_requests"))


@app.route("/checkin/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    """Let a user cancel their own booking before it's checked in."""
    if "username" not in session:
        return redirect(url_for("login"))

    if repo.cancel_booking(booking_id, session.get("username")):
        return redirect(url_for("checkin", message="Booking cancelled successfully."))

    return redirect(url_for("checkin"))


@app.route("/checkin/no-show/<int:booking_id>", methods=["POST"])
def mark_no_show(booking_id):
    """Let admin flag a guest who never arrived for a booking past its check-in date."""
    if not admin_required():
        return redirect(url_for("login"))

    if repo.mark_no_show(booking_id):
        return redirect(url_for("checkin", message="Booking marked as a no-show."))

    return redirect(url_for("checkin"))


@app.route("/checkin", methods=["GET", "POST"])
def checkin():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        if not admin_required():
            return redirect(url_for("login"))

        booking_id = request.form.get("booking_id")
        action = request.form.get("action")
        message = None

        try:
            booking_id = int(booking_id)
        except (TypeError, ValueError):
            return redirect(url_for("checkin"))

        booking = get_booking(booking_id)
        if booking is not None:
            if action == "checkin" and booking.get("status") == "Booked":
                checkin_booking(booking_id)
                message = "Booking checked in successfully."
            elif action == "checkout" and booking.get("status") == "Checked In":
                points_awarded = checkout_booking(booking_id)
                message = "Booking checked out successfully."
                if points_awarded:
                    message += f" {points_awarded} loyalty points awarded."

        if message:
            return redirect(url_for("checkin", message=message))
        return redirect(url_for("checkin"))

    message = request.args.get("message")
    search = request.args.get("search", "").strip()
    is_admin = session.get("role") == "admin"

    if is_admin:
        data = list_bookings()
    else:
        data = get_user_bookings(session.get("username"))
        search = ""

    matching_ids = None
    if is_admin and search:
        matching_ids = {b.get("id") for b in filter_bookings(data, search=search)}

    today = datetime.now().date()
    current_bookings = []
    past_bookings = []

    for booking in data:
        status = booking.get("status", "Booked")
        checkout = booking.get("checkout_date")
        is_past = False

        if status in ("Checked Out", "Cancelled", "No-Show"):
            is_past = True
        elif status == "Checked In":
            if checkout:
                try:
                    checkout_date = datetime.strptime(checkout, "%Y-%m-%d").date()
                    if checkout_date < today:
                        is_past = True
                except ValueError:
                    is_past = False

        booking["status_badge"] = get_booking_status_badge(status)
        booking["nights"] = get_booking_length(booking.get("checkin_date"), booking.get("checkout_date"))
        booking["days_until_checkin"] = get_booking_days_until(booking.get("checkin_date"), today)
        booking["is_today_arrival"] = booking.get("checkin_date") == today.strftime("%Y-%m-%d")
        booking["is_today_departure"] = booking.get("checkout_date") == today.strftime("%Y-%m-%d")

        if matching_ids is not None and booking.get("id") not in matching_ids:
            continue

        if is_past:
            past_bookings.append(booking)
        else:
            current_bookings.append(booking)

    dashboard = build_checkin_dashboard_data(data, role=session.get("role", "guest"), today=today)

    booked_bookings = []
    checkedin_bookings = []
    checkedout_bookings = []
    cancelled_bookings = []
    if not is_admin:
        for booking in data:
            status = booking.get("status", "Booked")
            if status == "Booked":
                booked_bookings.append(booking)
            elif status == "Checked In":
                checkedin_bookings.append(booking)
            elif status == "Checked Out":
                checkedout_bookings.append(booking)
            elif status in ("Cancelled", "No-Show"):
                cancelled_bookings.append(booking)

    return render_template(
        "checkin.html",
        current_bookings=current_bookings,
        past_bookings=past_bookings,
        booked_bookings=booked_bookings,
        checkedin_bookings=checkedin_bookings,
        checkedout_bookings=checkedout_bookings,
        cancelled_bookings=cancelled_bookings,
        bookings_count=len(data),
        message=message,
        dashboard=dashboard,
        search=search,
    )


def parse_rating(raw_value):
    """Parse a whole-number rating from 1 to 5. Return None when invalid."""
    try:
        value = int(str(raw_value).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    if value < 1 or value > 5:
        return None
    return value


@app.route("/feedback", methods=["GET", "POST"])
def guest_feedback():
    """Guest-facing feedback form linked to the logged-in customer's bookings."""
    if "username" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    username = session["username"]
    error = None
    booking_options = get_user_feedback_booking_options(username)

    if request.method == "POST":
        booking_id_raw = request.form.get("booking_id", "").strip()
        facilities_rating = parse_rating(request.form.get("facilities_rating", ""))
        amenities_rating = parse_rating(request.form.get("amenities_rating", ""))
        comfort_rating = parse_rating(request.form.get("comfort_cleanliness_rating", ""))
        additional_feedback = request.form.get("additional_feedback", "").strip()

        selected_booking = None
        try:
            booking_id = int(booking_id_raw)
            selected_booking = next(
                (b for b in get_user_bookings(username) if b.get("id") == booking_id),
                None,
            )
        except (TypeError, ValueError):
            selected_booking = None

        if selected_booking is None:
            error = "Please select one of your own bookings to give feedback for."
        elif feedback_exists_for_booking(selected_booking.get("id")):
            error = "Feedback has already been submitted for this booking."
        elif facilities_rating is None or amenities_rating is None or comfort_rating is None:
            error = (
                "Please rate facilities, amenities, and comfort/cleanliness "
                "using whole numbers from 1 (lowest) to 5 (highest)."
            )
        elif not additional_feedback:
            error = "Please share additional feedback or suggestions before submitting."
        elif len(additional_feedback) > MAX_FEEDBACK_LENGTH:
            error = f"Additional feedback must be {MAX_FEEDBACK_LENGTH} characters or fewer."
        else:
            new_entry = create_feedback(
                booking_id=selected_booking.get("id"),
                username=selected_booking.get("username") or username,
                guest_name=selected_booking.get("guest_name") or username,
                room_number=selected_booking.get("room_number", ""),
                room_type=selected_booking.get("room_type", ""),
                checkin_date=selected_booking.get("checkin_date", ""),
                checkout_date=selected_booking.get("checkout_date", ""),
                facilities_rating=facilities_rating,
                amenities_rating=amenities_rating,
                comfort_cleanliness_rating=comfort_rating,
                additional_feedback=additional_feedback,
            )
            return redirect(url_for("view_my_feedback", feedback_id=new_entry["id"], submitted=1))

    return render_template(
        "feedback_form.html",
        booking_options=booking_options,
        error=error,
        max_feedback_length=MAX_FEEDBACK_LENGTH,
    )


@app.route("/my-feedback")
def my_feedback():
    """Customer-facing list of feedback submitted by the logged-in guest."""
    if "username" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    username = session["username"]
    feedback_entries = get_user_submitted_feedback(username)
    has_eligible_booking = bool(get_user_feedback_booking_options(username))
    return render_template(
        "my_feedback.html",
        feedback_entries=feedback_entries,
        has_eligible_booking=has_eligible_booking,
    )


@app.route("/feedback/<int:feedback_id>")
def view_my_feedback(feedback_id):
    """View one submitted feedback record owned by the logged-in customer."""
    if "username" not in session or session.get("role") != "user":
        return redirect(url_for("login"))

    username = session["username"]
    entry = get_owned_feedback_by_id(feedback_id, username)
    if entry is None:
        return redirect(url_for("my_feedback"))

    just_submitted = request.args.get("submitted") == "1"
    return render_template(
        "feedback_view.html",
        entry=entry,
        just_submitted=just_submitted,
    )


@app.route("/admin/feedback")
def admin_feedback():
    """Staff-facing page for reviewing all guest feedback submissions."""
    if not admin_required():
        return redirect(url_for("login"))
    return render_template(
        "admin_feedback.html",
        feedback_entries=get_sorted_feedback(),
    )


@app.route("/api/feedback")
def api_feedback():
    """JSON feed of all feedback records, consumed by the admin feedback page."""
    if not admin_required():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(get_sorted_feedback())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
