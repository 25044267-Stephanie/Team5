from datetime import datetime, timedelta

import pytest

import app as hotel_app
import repository
from conftest import login_as
from factories import (
    make_booking,
    make_feedback,
    make_points_adjustment,
    make_request,
    make_room,
    make_user,
    set_points,
)
from models import db


def test_toiletries_request_non_peak_hour_estimate():
    assert False, "deliberate CI failure for Stage A gating demo"
    estimate = hotel_app.estimate_request_time(
        "Toiletries: Toothbrush x2",
        current_time=datetime(2024, 1, 1, 9, 0),
    )
    assert estimate == "5-10 minutes (non-peak hours)"


def test_toiletries_request_peak_hour_estimate():
    estimate = hotel_app.estimate_request_time(
        "Toiletries: Toothbrush x2",
        current_time=datetime(2024, 1, 1, 14, 0),
    )
    assert estimate == "10-15 minutes (peak hours)"


def test_food_and_beverage_request_peak_hour_estimate():
    estimate = hotel_app.estimate_request_time(
        "Food & Beverage: Meal: Chicken Burger",
        current_time=datetime(2024, 1, 1, 19, 0),
    )
    assert estimate == "30-40 minutes (peak hours)"


def test_repair_request_non_peak_hour_estimate():
    estimate = hotel_app.estimate_request_time(
        "Repair: Equipment: Television; Issue: no power",
        current_time=datetime(2024, 1, 1, 9, 0),
    )
    assert estimate == "60-120 minutes (non-peak hours)"


def test_other_request_non_peak_hour_estimate():
    estimate = hotel_app.estimate_request_time(
        "Other request: please arrange a taxi",
        current_time=datetime(2024, 1, 1, 9, 0),
    )
    assert estimate == "15-30 minutes (non-peak hours)"


def test_estimate_request_time_no_longer_accepts_a_priority_argument():
    # Priority now affects queue order (sort_requests_by_priority), never how
    # long a task physically takes, so the parameter was removed outright.
    with pytest.raises(TypeError):
        hotel_app.estimate_request_time(
            "Repair: Equipment: Television; Issue: no power",
            "High",
            current_time=datetime(2024, 1, 1, 9, 0),
        )


def test_get_remaining_estimate_display_counts_down_as_time_passes():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=20)).isoformat()
    req = {"created_at": created, "estimated_min": 60, "estimated_max": 120}

    remaining = hotel_app.get_remaining_estimate_display(req, now=now)

    assert remaining == "40-100 minutes remaining"


def test_get_remaining_estimate_display_floors_min_at_zero():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=70)).isoformat()
    req = {"created_at": created, "estimated_min": 60, "estimated_max": 120}

    remaining = hotel_app.get_remaining_estimate_display(req, now=now)

    assert remaining == "Up to 50 minutes remaining"


def test_get_remaining_estimate_display_shows_any_moment_once_past_max():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=130)).isoformat()
    req = {"created_at": created, "estimated_min": 60, "estimated_max": 120}

    remaining = hotel_app.get_remaining_estimate_display(req, now=now)

    assert remaining == "Any moment now"


def test_get_remaining_estimate_display_falls_back_to_static_estimate_when_range_missing():
    req = {"estimated_time": "10-15 minutes (non-peak hours)"}

    remaining = hotel_app.get_remaining_estimate_display(req)

    assert remaining == "10-15 minutes (non-peak hours)"


def test_get_user_room_number_from_booking():
    make_booking(username="user", room_number="205")
    assert repository.get_user_room_number("user") == "205"


def test_get_user_room_number_with_no_bookings_returns_na():
    assert repository.get_user_room_number("user") == "N/A"


def test_accept_all_pending_requests_marks_them_accepted():
    make_request(username="user", message="Please send towels", status="Pending")
    make_request(username="user", message="Need extra pillows", status="Pending")
    make_request(username="user", message="Already handled", status="Accepted")

    accepted_count = repository.accept_all_requests(hotel_app._estimate_minutes_range)

    assert accepted_count == 2
    statuses = [r["status"] for r in repository.list_requests()]
    assert statuses.count("Accepted") == 3  # 2 newly accepted + the 1 already accepted


def test_sort_requests_by_priority_puts_high_first():
    requests = [
        {"id": 1, "priority": "Low", "status": "Pending"},
        {"id": 2, "priority": "High", "status": "Pending"},
        {"id": 3, "priority": "Medium", "status": "Pending"},
    ]

    sorted_requests = hotel_app.sort_requests_by_priority(requests)

    assert [req["id"] for req in sorted_requests] == [2, 3, 1]


def test_sort_requests_by_priority_breaks_ties_by_arrival_order():
    requests = [
        {"id": 1, "priority": "High", "status": "Pending"},
        {"id": 2, "priority": "High", "status": "Pending"},
        {"id": 3, "priority": "High", "status": "Pending"},
    ]

    sorted_requests = hotel_app.sort_requests_by_priority(requests)

    assert [req["id"] for req in sorted_requests] == [1, 2, 3]


def test_sort_requests_by_priority_reflects_wait_time_escalation():
    # A Low request that has waited 35 real minutes auto-escalates to Medium
    # and ties with the already-Medium request (arrival order keeps id 1
    # first); the still-fresh Low stays last. This replaces the old
    # per-render "wait count" aging with a real timestamp-based mechanism.
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    stale_low_created = (now - timedelta(minutes=35)).isoformat()
    fresh_created = now.isoformat()

    requests = [
        {"id": 1, "priority": "Medium", "status": "Pending", "created_at": fresh_created},
        {"id": 2, "priority": "Low", "status": "Pending", "created_at": stale_low_created},
        {"id": 3, "priority": "Low", "status": "Pending", "created_at": fresh_created},
    ]

    order = [req["id"] for req in hotel_app.sort_requests_by_priority(requests, now=now)]

    assert order == [1, 2, 3]


def test_sort_requests_by_priority_breaks_equal_priority_ties_by_room_type():
    requests = [
        {"id": 1, "priority": "Medium", "status": "Pending", "room_type": "Single"},
        {"id": 2, "priority": "Medium", "status": "Pending", "room_type": "Suite"},
        {"id": 3, "priority": "Medium", "status": "Pending", "room_type": "Double"},
    ]

    order = [req["id"] for req in hotel_app.sort_requests_by_priority(requests)]

    assert order == [2, 3, 1]


def test_get_effective_priority_escalates_low_to_medium_after_30_minutes():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=31)).isoformat()

    label, escalated = hotel_app.get_effective_priority({"priority": "Low", "created_at": created}, now=now)

    assert label == "Medium"
    assert escalated is True


def test_get_effective_priority_keeps_low_before_threshold():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=29)).isoformat()

    label, escalated = hotel_app.get_effective_priority({"priority": "Low", "created_at": created}, now=now)

    assert label == "Low"
    assert escalated is False


def test_get_effective_priority_escalates_low_all_the_way_to_high_after_50_minutes():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=51)).isoformat()

    label, escalated = hotel_app.get_effective_priority({"priority": "Low", "created_at": created}, now=now)

    assert label == "High"
    assert escalated is True


def test_get_effective_priority_escalates_medium_to_high_after_20_minutes():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=hotel_app.SINGAPORE_TZ)
    created = (now - timedelta(minutes=21)).isoformat()

    label, escalated = hotel_app.get_effective_priority({"priority": "Medium", "created_at": created}, now=now)

    assert label == "High"
    assert escalated is True


def test_determine_request_priority_defaults_by_category():
    assert hotel_app.determine_request_priority("Repair", "Repair: Equipment: TV; Issue: no picture") == "High"
    assert hotel_app.determine_request_priority("Food & Beverage", "Food & Beverage: Meal: Chicken Burger") == "Medium"
    assert hotel_app.determine_request_priority("Toiletries", "Toiletries: Soap x1") == "Low"
    assert hotel_app.determine_request_priority("Other", "Other request: extra pillow") == "Low"


def test_determine_request_priority_escalates_on_urgent_keywords_regardless_of_category():
    assert hotel_app.determine_request_priority("Other", "Other request: there is a water leak in the bathroom") == "High"
    assert hotel_app.determine_request_priority("Toiletries", "Toiletries: help, I'm locked out of my room") == "High"


def test_sort_requests_by_priority_guarantees_medium_and_low_within_first_batch():
    # Even with many Highs waiting, Medium and Low must not be starved beyond
    # the first batch of 5 served requests.
    requests = [
        {"id": i, "priority": "High", "status": "Pending"} for i in range(1, 7)
    ] + [
        {"id": 7, "priority": "Medium", "status": "Pending"},
        {"id": 8, "priority": "Low", "status": "Pending"},
    ]

    order = [req["id"] for req in hotel_app.sort_requests_by_priority(requests)]
    first_batch = order[:5]

    assert 7 in first_batch
    assert 8 in first_batch


def test_sort_requests_by_priority_keeps_non_pending_requests_after_scheduled_ones():
    requests = [
        {"id": 1, "priority": "Low", "status": "Accepted"},
        {"id": 2, "priority": "High", "status": "Pending"},
        {"id": 3, "priority": "Low", "status": "Pending"},
    ]

    order = [req["id"] for req in hotel_app.sort_requests_by_priority(requests)]

    assert order == [2, 3, 1]


def test_cancel_user_request_marks_pending_request_cancelled():
    req1 = make_request(username="user", status="Pending")
    make_request(username="user", status="Accepted")

    cancelled = hotel_app.cancel_user_request(req1["id"], "user")

    assert cancelled is True
    updated = repository.get_request(req1["id"])
    assert updated["status"] == "Cancelled"
    assert updated["cancelled_by"] == "user"


def test_prevents_overlapping_room_bookings():
    room = make_room(2)
    make_booking(room_id=room["id"], checkin_date="2024-01-01", checkout_date="2024-01-03", status="Booked")

    is_available = hotel_app.is_room_available(
        room_id=room["id"],
        checkin_date="2024-01-02",
        checkout_date="2024-01-04",
    )

    assert is_available is False


def test_is_room_available_excludes_the_booking_being_edited():
    room = make_room(2)
    booking = make_booking(
        room_id=room["id"], checkin_date="2024-01-01", checkout_date="2024-01-03", status="Booked",
    )

    # Without excluding itself, a booking always conflicts with its own dates.
    assert hotel_app.is_room_available(room_id=room["id"], checkin_date="2024-01-01", checkout_date="2024-01-03") is False

    # Excluding the booking being edited lets it keep (or adjust) its own dates.
    assert hotel_app.is_room_available(
        room_id=room["id"], checkin_date="2024-01-01", checkout_date="2024-01-03", exclude_booking_id=booking["id"],
    ) is True

    # A genuine conflict with a DIFFERENT booking is still caught.
    make_booking(room_id=room["id"], checkin_date="2024-01-02", checkout_date="2024-01-05", status="Booked")
    assert hotel_app.is_room_available(
        room_id=room["id"], checkin_date="2024-01-01", checkout_date="2024-01-03", exclude_booking_id=booking["id"],
    ) is False


def test_same_first_name_different_last_name_are_stored_separately():
    make_user("guest1")
    make_user("guest2")
    room1 = make_room(2, room_type="Double", price=120)
    room2 = make_room(41, room_type="Suite", price=200)

    first_booking = repository.create_booking(
        room_id=room1["id"], room_number=room1["room_number"], room_type=room1["type"], price=120,
        checkin_date="2024-02-01", checkout_date="2024-02-03", username="guest1",
        guest_first_name="John", guest_last_name="Smith",
        phone_number="91234567", email="john.smith@example.com",
    )
    second_booking = repository.create_booking(
        room_id=room2["id"], room_number=room2["room_number"], room_type=room2["type"], price=200,
        checkin_date="2024-02-04", checkout_date="2024-02-06", username="guest2",
        guest_first_name="John", guest_last_name="Doe",
        phone_number="98765432", email="john.doe@example.com",
    )

    assert first_booking["guest_name"] == "John Smith"
    assert second_booking["guest_name"] == "John Doe"
    assert first_booking["guest_name"] != second_booking["guest_name"]


def test_get_user_booked_room_options_only_returns_checked_in_bookings():
    make_booking(username="user", room_number="101", guest_name="Jane Doe", status="Booked")
    make_booking(username="user", room_number="205", guest_name="Jane Doe", status="Checked In")

    options = hotel_app.get_user_booked_room_options("user")

    assert len(options) == 1
    assert options[0]["value"] == "205"
    assert options[0]["label"] == "Room 205 - Jane Doe"


def test_get_room_options_returns_all_rooms_for_request_reference():
    make_room(2, room_type="Single", status="Available")
    make_room(3, room_type="Double", status="Available")

    options = repository.get_room_options()

    assert len(options) == 2
    assert options[0]["value"] == "2"
    assert "Single" in options[0]["label"]


def test_reset_user_password_updates_password_and_allows_login():
    make_user("guest", password="oldpass")

    success, message = hotel_app.reset_user_password("guest", "newpass123")

    assert success is True
    assert message == "Password reset successfully."
    assert hotel_app.verify_user_password(repository.get_user("guest"), "newpass123") is True


def test_filter_rooms_by_room_type_returns_only_matching_rooms():
    rooms = [
        {"room_number": "101", "type": "Single", "status": "Available"},
        {"room_number": "102", "type": "Double", "status": "Available"},
        {"room_number": "103", "type": "Suite", "status": "Available"},
    ]

    filtered = hotel_app.filter_rooms_by_type(rooms, "Double")

    assert len(filtered) == 1
    assert filtered[0]["type"] == "Double"


def test_create_room_rejects_numbers_outside_one_to_fifty():
    # Replaces the old JSON-catalogue-migration test (normalize_rooms no
    # longer exists — the database itself now enforces 1-50 via a CHECK
    # constraint, and create_room rejects anything derive_room_details can't
    # place before it ever reaches the database).
    assert repository.create_room("101") is None
    assert repository.list_rooms() == []


def test_room_number_rules_cover_all_three_room_types():
    assert hotel_app.derive_room_details(2)["type"] == "Single"
    assert hotel_app.derive_room_details(2)["price"] == 100
    assert hotel_app.derive_room_details(1)["type"] == "Double"
    assert hotel_app.derive_room_details(1)["price"] == 200
    assert hotel_app.derive_room_details(41)["type"] == "Suite"
    assert hotel_app.derive_room_details(41)["price"] == 500


def test_room_number_rules_reject_numbers_outside_one_to_fifty():
    assert hotel_app.derive_room_details(0) is None
    assert hotel_app.derive_room_details(51) is None
    assert hotel_app.derive_room_details("letters") is None


def test_remove_past_bookings_only_removes_old_entries():
    make_booking(id=1, checkin_date="2023-12-30", checkout_date="2024-01-01", status="Checked Out")
    make_booking(id=2, checkin_date="2099-01-01", checkout_date="2099-01-03", status="Booked")

    removed_count = repository.remove_past_bookings(today=datetime(2024, 6, 1).date())

    assert removed_count == 1
    remaining = repository.list_bookings()
    assert len(remaining) == 1
    assert remaining[0]["id"] == 2


def test_calculate_loyalty_points_by_room_type_and_nights():
    assert repository.calculate_loyalty_points("Single", 2) == 20
    assert repository.calculate_loyalty_points("Double", 3) == 60
    assert repository.calculate_loyalty_points("Suite", 1) == 50
    assert repository.calculate_loyalty_points("Single", 0) == 0
    assert repository.calculate_loyalty_points("Single", None) == 0
    assert repository.calculate_loyalty_points("Unknown", 5) == 0


def test_checkout_booking_credits_user_and_marks_booking():
    room = make_room(1, room_type="Double", price=200)
    booking = make_booking(
        username="user", room_id=room["id"], room_number=room["room_number"], room_type="Double",
        checkin_date="2026-07-01", checkout_date="2026-07-04", status="Checked In",
    )

    awarded = repository.checkout_booking(booking["id"])

    assert awarded == 60  # Double = 20/night * 3 nights
    updated = repository.get_booking(booking["id"])
    assert updated["points_awarded"] is True
    assert repository.get_user("user")["points"] == 60


def test_checkout_booking_never_awards_twice():
    room = make_room(41, room_type="Suite", price=500)
    booking = make_booking(
        username="user", room_id=room["id"], room_number=room["room_number"], room_type="Suite",
        checkin_date="2026-07-01", checkout_date="2026-07-02", status="Checked In",
    )

    first = repository.checkout_booking(booking["id"])
    second = repository.checkout_booking(repository.get_booking(booking["id"])["id"])

    assert first == 50
    assert second is None  # already checked out — not eligible again
    assert repository.get_user("user")["points"] == 50


def _sample_admin_bookings():
    return [
        {"id": 1, "username": "user", "guest_name": "Alex Guest", "room_number": "101", "room_type": "Single",
         "phone_number": "91234567", "email": "alex@example.com", "checkin_date": "2026-08-01", "checkout_date": "2026-08-03", "status": "Booked"},
        {"id": 2, "username": "user2", "guest_name": "Jamie Lee", "room_number": "205", "room_type": "Suite",
         "phone_number": "98765432", "email": "jamie@example.com", "checkin_date": "2026-08-05", "checkout_date": "2026-08-07", "status": "Checked In"},
        {"id": 3, "username": "user3", "guest_name": "Sam Tan", "room_number": "310", "room_type": "Double",
         "phone_number": "96665555", "email": "sam@example.com", "checkin_date": "2026-08-10", "checkout_date": "2026-08-12", "status": "Checked Out"},
    ]


def test_filter_bookings_search_is_case_insensitive_across_fields():
    data = _sample_admin_bookings()

    assert [b["id"] for b in hotel_app.filter_bookings(data, search="JAMIE")] == [2]  # guest name
    assert [b["id"] for b in hotel_app.filter_bookings(data, search="alex@example.com")] == [1]  # email
    assert [b["id"] for b in hotel_app.filter_bookings(data, search="96665555")] == [3]  # phone number
    assert [b["id"] for b in hotel_app.filter_bookings(data, search="205")] == [2]  # room number
    assert [b["id"] for b in hotel_app.filter_bookings(data, search="")] == [1, 2, 3]  # blank search matches all


def test_filter_bookings_search_matches_booking_id():
    # Deliberately non-overlapping digits in the other fields so this isolates
    # a match coming specifically from the booking id.
    data = [
        {"id": 42, "guest_name": "No Match Here", "room_number": "999", "phone_number": "00000000", "email": "x@x.com"},
        {"id": 7, "guest_name": "Also No Match", "room_number": "888", "phone_number": "11111111", "email": "y@y.com"},
    ]

    assert [b["id"] for b in hotel_app.filter_bookings(data, search="42")] == [42]


def test_filter_bookings_status_and_room_type_are_combinable():
    data = _sample_admin_bookings()

    assert [b["id"] for b in hotel_app.filter_bookings(data, status="Checked In")] == [2]
    assert [b["id"] for b in hotel_app.filter_bookings(data, room_type="Suite")] == [2]
    assert [b["id"] for b in hotel_app.filter_bookings(data, status="Checked In", room_type="Suite")] == [2]
    assert hotel_app.filter_bookings(data, status="Checked In", room_type="Single") == []


def test_filter_bookings_date_filters():
    data = _sample_admin_bookings()

    assert [b["id"] for b in hotel_app.filter_bookings(data, checkin_date="2026-08-05")] == [2]
    assert [b["id"] for b in hotel_app.filter_bookings(data, checkout_date="2026-08-12")] == [3]


def test_paginate_list_splits_into_pages_and_clamps_page_number():
    items = list(range(1, 26))  # 25 items

    page_items, total_pages, page = hotel_app.paginate_list(items, page=1, per_page=10)
    assert page_items == list(range(1, 11))
    assert total_pages == 3
    assert page == 1

    page_items_2, _, page_2 = hotel_app.paginate_list(items, page=3, per_page=10)
    assert page_items_2 == [21, 22, 23, 24, 25]
    assert page_2 == 3

    # Out-of-range page numbers clamp into the valid range instead of erroring.
    _, _, clamped_high = hotel_app.paginate_list(items, page=99, per_page=10)
    assert clamped_high == 3
    _, _, clamped_low = hotel_app.paginate_list(items, page=0, per_page=10)
    assert clamped_low == 1


def test_build_checkin_dashboard_data_includes_pending_and_checked_out_counts():
    bookings = [
        {"status": "Booked", "checkin_date": "2026-07-13", "checkout_date": "2026-07-15"},
        {"status": "Checked In", "checkin_date": "2026-07-12", "checkout_date": "2026-07-12"},
        {"status": "Checked Out", "checkin_date": "2026-07-01", "checkout_date": "2026-07-03"},
        {"status": "Checked Out", "checkin_date": "2026-07-02", "checkout_date": "2026-07-04"},
    ]

    summary = hotel_app.build_checkin_dashboard_data(bookings, role="admin", today=datetime(2026, 7, 12).date())

    assert summary["pending_count"] == 1
    assert summary["checked_out_count"] == 2


def test_get_booking_status_badge_returns_expected_class():
    badge = hotel_app.get_booking_status_badge("Checked In")

    assert badge["label"] == "Checked In"
    assert badge["class"] == "status-badge status-checkedin"


def test_build_checkin_dashboard_data_returns_summary_counts():
    bookings = [
        {"status": "Booked", "checkin_date": "2026-07-13", "checkout_date": "2026-07-15"},
        {"status": "Checked In", "checkin_date": "2026-07-12", "checkout_date": "2026-07-12"},
        {"status": "Checked Out", "checkin_date": "2026-07-01", "checkout_date": "2026-07-03"},
    ]

    summary = hotel_app.build_checkin_dashboard_data(
        bookings,
        role="admin",
        today=datetime(2026, 7, 12).date(),
    )

    assert summary["total_bookings"] == 3
    assert summary["checked_in_count"] == 1
    assert summary["arrivals_today"] == 1
    assert summary["departures_today"] == 1
    assert summary["occupancy_rate"] == 33


def test_build_request_message_for_toiletries_includes_selected_items_and_quantities():
    form_data = {
        "request_type": "Toiletries",
        "toiletry_toothbrush": "2",
        "toiletry_shampoo": "1",
        "toiletry_soap": "0",
        "toiletry_conditioner": "4",
    }

    message = hotel_app.build_request_message(form_data)

    assert "Toiletries" in message
    assert "Toothbrush x2" in message
    assert "Shampoo x1" in message
    assert "Conditioner x4" in message


def test_validate_request_form_rejects_toiletry_quantities_above_five():
    form_data = {
        "request_type": "Toiletries",
        "toiletry_toothbrush": "6",
        "toiletry_shampoo": "1",
        "toiletry_soap": "0",
        "toiletry_conditioner": "4",
    }

    error = hotel_app.validate_request_form(form_data)

    assert error == "Please enter the correct quantity which is 1-5."


def test_validate_request_form_rejects_toiletry_quantities_below_one():
    form_data = {
        "request_type": "Toiletries",
        "toiletry_toothbrush": "-1",
        "toiletry_shampoo": "1",
        "toiletry_soap": "2",
        "toiletry_conditioner": "4",
    }

    error = hotel_app.validate_request_form(form_data)

    assert error == "Please enter the correct quantity which is 1-5."


def test_validate_request_form_allows_unselected_toiletries_left_at_default_zero():
    form_data = {
        "request_type": "Toiletries",
        "toiletry_toothbrush": "2",
        "toiletry_shampoo": "0",
        "toiletry_soap": "0",
        "toiletry_conditioner": "0",
    }

    error = hotel_app.validate_request_form(form_data)

    assert error is None


def test_build_request_message_for_food_and_beverage_includes_meal_components():
    form_data = {
        "request_type": "Food & Beverage",
        "food_item": "Chicken Burger",
        "drink": "Orange Juice",
        "soup": "Tomato Soup",
        "dessert": "Chocolate Cake",
    }

    message = hotel_app.build_request_message(form_data)

    assert "Food & Beverage" in message
    assert "Meal: Chicken Burger" in message
    assert "Drink: Orange Juice" in message
    assert "Soup: Tomato Soup" in message
    assert "Dessert: Chocolate Cake" in message


def test_build_request_message_for_repair_records_equipment_and_issue():
    form_data = {
        "request_type": "Repair",
        "repair_equipment": "Air Conditioner",
        "repair_issue": "Not cooling",
    }

    message = hotel_app.build_request_message(form_data)

    assert "Repair" in message
    assert "Air Conditioner" in message
    assert "Not cooling" in message


def test_build_request_message_for_other_uses_custom_text_input():
    form_data = {
        "request_type": "Other",
        "other_request_text": "Need extra pillows for my child",
    }

    message = hotel_app.build_request_message(form_data)

    assert "Other request" in message
    assert "Need extra pillows for my child" in message


def test_preview_and_saved_room_image_use_same_mapping_for_every_room_type():
    sample_rooms = (20, 23, 48)

    for room_number in sample_rooms:
        details = hotel_app.derive_room_details(room_number)
        assert details["image"] == repository.get_room_image(details["type"], room_number)


def test_room_image_distribution_remains_even_for_the_full_catalogue():
    image_counts = {
        "Single": {},
        "Double": {},
        "Suite": {},
    }

    for room_number in range(1, 51):
        details = hotel_app.derive_room_details(room_number)
        room_type = details["type"]
        image = details["image"]
        image_counts[room_type][image] = image_counts[room_type].get(image, 0) + 1

    assert sorted(image_counts["Single"].values()) == [10, 10]
    assert sorted(image_counts["Double"].values()) == [10, 10]
    assert sorted(image_counts["Suite"].values()) == [5, 5]


def test_admin_bookings_page_combines_search_filter_and_pagination(client):
    for i in range(1, 13):
        make_booking(
            username="user", guest_name=f"Guest {i}", room_number=str(100 + i), room_type="Single",
            phone_number="91234567", email=f"guest{i}@example.com",
            checkin_date="2026-08-01", checkout_date="2026-08-03", status="Booked",
        )
    make_booking(
        username="user", guest_name="Jamie Lee", room_number="205", room_type="Suite",
        phone_number="98765432", email="jamie@example.com",
        checkin_date="2026-08-05", checkout_date="2026-08-07", status="Checked In",
    )

    login_as(client, "admin", "admin123")

    # Pagination: 13 total bookings, 10 per page -> page 1 has 10, page 2 has 3.
    page1 = client.get("/bookings")
    page2 = client.get("/bookings?page=2")
    assert page1.data.count(b"btn-small view-booking-btn") == 10
    assert page2.data.count(b"btn-small view-booking-btn") == 3

    # Search + status + room_type combine to isolate exactly Jamie's booking.
    combined = client.get("/bookings?search=jamie&status=Checked In&room_type=Suite")
    assert combined.data.count(b"btn-small view-booking-btn") == 1
    assert b"Jamie Lee" in combined.data

    # Summary cards reflect the full unfiltered set, not the filtered view.
    assert b"13" in combined.data  # total_bookings stat card


def test_bookings_export_csv_reflects_current_filters(client):
    make_booking(
        username="user", guest_name="Alex Guest", room_number="101", room_type="Single",
        phone_number="91234567", email="alex@example.com",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Booked",
    )
    make_booking(
        username="user", guest_name="Jamie Lee", room_number="205", room_type="Suite",
        phone_number="98765432", email="jamie@example.com",
        checkin_date="2026-08-05", checkout_date="2026-08-07", status="Checked In",
    )

    login_as(client, "admin", "admin123")
    response = client.get("/bookings/export?status=Checked In")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert "attachment" in response.headers["Content-Disposition"]
    csv_text = response.data.decode()
    assert "Jamie Lee" in csv_text
    assert "Alex Guest" not in csv_text


def test_guest_cannot_reach_admin_export_route(client):
    login_as(client, "user", "user123")
    response = client.get("/bookings/export", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_guest_bookings_view_is_unaffected_by_the_admin_pms_rebuild(client):
    make_user("someone_else")
    make_booking(
        username="user", guest_name="Alex Guest", room_number="12", room_type="Single",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Booked",
    )
    make_booking(
        username="someone_else", guest_name="Other Guest", room_number="13", room_type="Double",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Booked",
    )

    login_as(client, "user", "user123")
    response = client.get("/bookings")

    assert response.status_code == 200
    assert b"Alex Guest" in response.data
    assert b"Other Guest" not in response.data  # still scoped to the guest's own bookings only
    assert b"booking-item" in response.data  # still the original card layout
    assert b"Total Bookings" not in response.data  # no admin PMS chrome leaked in
    assert b"bookings-table" not in response.data


def test_existing_checkin_and_remove_past_routes_still_work_after_pms_rebuild(client):
    room = make_room(12, room_type="Single", status="Booked")
    make_booking(
        username="user", guest_name="Alex Guest", room_id=room["id"], room_number="12", room_type="Single",
        checkin_date="2020-01-01", checkout_date="2020-01-03", status="Booked",
    )

    client.post("/login", data={"username": "admin", "password": "admin123"})

    checkin_response = client.post("/checkin", data={"booking_id": "1", "action": "checkin"}, follow_redirects=True)
    assert checkin_response.status_code == 200
    assert repository.get_booking(1)["status"] == "Checked In"

    remove_past_response = client.get("/bookings/remove-past", follow_redirects=True)
    assert remove_past_response.status_code == 200
    # checkout_date is in the past, so remove-past-bookings deletes it, same as before.
    assert repository.list_bookings() == []


def test_bookings_page_no_longer_shows_remove_past_bookings_button(client):
    make_booking(
        username="user", guest_name="Alex Guest", room_number="12", room_type="Single",
        checkin_date="2020-01-01", checkout_date="2020-01-03", status="Booked",
    )

    login_as(client, "admin", "admin123")
    response = client.get("/bookings")

    assert b"Remove Past Bookings" not in response.data
    assert b'id="remove-past-trigger"' not in response.data


def test_edit_booking_get_shows_form_for_an_active_booking(client):
    make_booking(
        username="user", guest_name="Alex Guest", guest_first_name="Alex", guest_last_name="Guest",
        room_number="12", room_type="Single", phone_number="91234567", email="alex@example.com",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Checked In",
    )

    login_as(client, "admin", "admin123")
    response = client.get("/admin/bookings/edit/1")

    assert response.status_code == 200
    assert b'value="Alex"' in response.data
    assert b'value="91234567"' in response.data


def test_edit_booking_locked_once_checked_out(client):
    make_booking(
        username="user", guest_name="Alex Guest", room_number="12", room_type="Single",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Checked Out",
    )

    login_as(client, "admin", "admin123")

    get_response = client.get("/admin/bookings/edit/1", follow_redirects=False)
    assert get_response.status_code == 302
    assert "/bookings" in get_response.headers.get("Location", "")

    post_response = client.post(
        "/admin/bookings/edit/1",
        data={
            "guest_first_name": "Changed", "guest_last_name": "Name",
            "phone_number": "91234567", "email": "changed@example.com",
            "checkin_date": "2026-09-01", "checkout_date": "2026-09-03",
        },
        follow_redirects=False,
    )
    assert post_response.status_code == 302
    # Nothing was modified - the checked-out booking is left exactly as-is.
    updated = repository.get_booking(1)
    assert updated["guest_name"] == "Alex Guest"
    assert updated["checkin_date"] == "2026-08-01"


def test_edit_booking_post_updates_guest_details_and_dates(client):
    make_booking(
        username="user", guest_name="Alex Guest", guest_first_name="Alex", guest_last_name="Guest",
        room_number="12", room_type="Single", phone_number="91234567", email="alex@example.com",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Checked In",
    )

    login_as(client, "admin", "admin123")
    response = client.post(
        "/admin/bookings/edit/1",
        data={
            "guest_first_name": "Alexandra", "guest_last_name": "Guest-Smith",
            "phone_number": "98887777", "email": "alexandra@example.com",
            "checkin_date": "2026-08-02", "checkout_date": "2026-08-05",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    updated = repository.get_booking(1)
    assert updated["guest_name"] == "Alexandra Guest-Smith"
    assert updated["phone_number"] == "98887777"
    assert updated["email"] == "alexandra@example.com"
    assert updated["checkin_date"] == "2026-08-02"
    assert updated["checkout_date"] == "2026-08-05"
    # Editing must never touch status or points bookkeeping.
    assert updated["status"] == "Checked In"


def test_edit_booking_post_rejects_invalid_phone_number(client):
    make_booking(
        username="user", guest_name="Alex Guest", room_number="12", room_type="Single",
        phone_number="91234567", email="alex@example.com",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Checked In",
    )

    login_as(client, "admin", "admin123")
    response = client.post(
        "/admin/bookings/edit/1",
        data={
            "guest_first_name": "Alex", "guest_last_name": "Guest",
            "phone_number": "12345", "email": "alex@example.com",
            "checkin_date": "2026-08-01", "checkout_date": "2026-08-03",
        },
    )

    assert response.status_code == 200
    assert b"Phone number must be exactly 8 digits" in response.data
    assert repository.get_booking(1)["phone_number"] == "91234567"


def test_edit_booking_post_rejects_dates_overlapping_another_booking(client):
    room = make_room(12, room_type="Single")
    make_booking(
        username="user", guest_name="Alex Guest", room_id=room["id"], room_number="12", room_type="Single",
        phone_number="91234567", email="alex@example.com",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Checked In",
    )
    make_user("user2")
    make_booking(
        username="user2", guest_name="Other Guest", room_id=room["id"], room_number="12", room_type="Single",
        phone_number="98887777", email="other@example.com",
        checkin_date="2026-08-10", checkout_date="2026-08-12", status="Booked",
    )

    login_as(client, "admin", "admin123")
    response = client.post(
        "/admin/bookings/edit/1",
        data={
            "guest_first_name": "Alex", "guest_last_name": "Guest",
            "phone_number": "91234567", "email": "alex@example.com",
            "checkin_date": "2026-08-11", "checkout_date": "2026-08-13",
        },
    )

    assert response.status_code == 200
    assert b"already booked for the selected dates" in response.data
    assert repository.get_booking(1)["checkin_date"] == "2026-08-01"


def test_guest_cannot_access_edit_booking_route(client):
    make_booking(
        username="user", guest_name="Alex Guest", room_number="12", room_type="Single",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Booked",
    )

    login_as(client, "user", "user123")
    response = client.get("/admin/bookings/edit/1", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_bookings_table_edit_button_disabled_only_once_checked_out(client):
    make_booking(
        username="user", guest_name="Active Guest", room_number="12", room_type="Single",
        checkin_date="2026-08-01", checkout_date="2026-08-03", status="Checked In",
    )
    make_booking(
        username="user", guest_name="Done Guest", room_number="13", room_type="Double",
        checkin_date="2026-07-01", checkout_date="2026-07-03", status="Checked Out",
    )

    login_as(client, "admin", "admin123")
    response = client.get("/bookings")
    html = response.data.decode()

    assert '/admin/bookings/edit/1' in html
    assert '/admin/bookings/edit/2' not in html
    assert "Only checked-in bookings can be edited" in html


def test_admin_checkout_awards_points_exactly_once(client):
    room = make_room(12, room_type="Double", status="Occupied")
    make_booking(
        username="user", guest_name="Alex Guest", room_id=room["id"], room_number="12", room_type="Double",
        checkin_date="2026-07-01", checkout_date="2026-07-04", status="Checked In",
    )

    client.post("/login", data={"username": "admin", "password": "admin123"})
    response = client.post("/checkin", data={"booking_id": "1", "action": "checkout"}, follow_redirects=True)

    assert response.status_code == 200
    updated = repository.get_booking(1)
    assert updated["status"] == "Checked Out"
    assert updated["points_awarded"] is True
    assert repository.get_user("user")["points"] == 60  # Double = 20/night * 3 nights

    # Repeating the checkout action (already Checked Out) must never award twice.
    client.post("/checkin", data={"booking_id": "1", "action": "checkout"})
    assert repository.get_user("user")["points"] == 60


def test_checkout_action_grants_no_points_for_ineligible_statuses(client):
    room = make_room(12, room_type="Suite", status="Available")

    client.post("/login", data={"username": "admin", "password": "admin123"})

    for ineligible_status in ("Booked", "Cancelled"):
        db.session.query(repository.Booking).delete()
        db.session.commit()
        make_booking(
            id=1, username="user", room_id=room["id"], room_number="12", room_type="Suite",
            checkin_date="2026-07-01", checkout_date="2026-07-03", status=ineligible_status,
        )
        client.post("/checkin", data={"booking_id": "1", "action": "checkout"})

        updated = repository.get_booking(1)
        assert updated["status"] == ineligible_status
        assert updated["points_awarded"] is False

    assert repository.get_user("user")["points"] == 0


def test_loyalty_points_persist_after_data_reload():
    # Replaces the old JSON round-trip test — the "reload" is now proven by
    # expiring SQLAlchemy's identity map and re-querying MySQL from scratch,
    # rather than dumping to and reloading data.json.
    make_user("newguest", points=75)
    set_points("user", 150)

    db.session.expire_all()

    assert repository.get_user("user")["points"] == 150
    assert repository.get_user("newguest")["points"] == 75
    assert repository.get_user("admin")["points"] == 0


def test_guest_dashboard_shows_loyalty_points_balance(client):
    set_points("user", 230)

    client.post("/login", data={"username": "user", "password": "user123"})
    response = client.get("/user/dashboard")

    assert response.status_code == 200
    assert b"Loyalty Points" in response.data
    assert b"230" in response.data


def test_submitting_request_records_category_created_at_and_auto_priority(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    response = client.post(
        "/requests",
        data={
            "room_number": "12",
            "request_type": "Repair",
            "repair_equipment": "Air Conditioner",
            "repair_issue": "Not cooling",
        },
    )

    # Redirects after a successful submission (POST/Redirect/GET) so that
    # refreshing the page doesn't resubmit the form and create a duplicate.
    assert response.status_code == 302
    requests_list = repository.get_user_requests("user")
    assert len(requests_list) == 1

    created = requests_list[0]
    assert created["category"] == "Repair"
    assert created["priority"] == "High"
    assert "T" in created["created_at"]
    assert created["estimated_min"] > 0
    assert created["estimated_max"] > created["estimated_min"]


def test_refreshing_after_submission_does_not_duplicate_the_request(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    client.post(
        "/requests",
        data={
            "room_number": "12",
            "request_type": "Toiletries",
            "toiletry_toothbrush": "1",
        },
    )

    assert len(repository.get_user_requests("user")) == 1

    # Simulate the browser following the redirect (what a page refresh does)
    # instead of resubmitting the POST body.
    client.get("/requests")
    client.get("/requests")

    assert len(repository.get_user_requests("user")) == 1


def test_reservation_request_queue_numbers_start_at_one_and_increment():
    # Replaces the old next_queue_number()-based tests. Queue numbers are now
    # simply the row's auto-increment id, which is inherently sequential and
    # never reused — verified end-to-end (through the real /requests route)
    # by test_cancelled_ticket_number_is_never_reused_end_to_end below.
    first = make_request(username="user")
    second = make_request(username="user")

    assert first["queue_number"] == first["id"]
    assert second["queue_number"] == second["id"]
    assert second["queue_number"] == first["queue_number"] + 1


def test_parse_request_line_items_splits_toiletries_message():
    items = hotel_app.parse_request_line_items("Toiletries: Toothbrush x2; Shampoo x1")
    assert items == ["Toothbrush x2", "Shampoo x1"]


def test_parse_request_line_items_splits_food_and_beverage_message():
    items = hotel_app.parse_request_line_items("Food & Beverage: Meal: Chicken Burger; Drink: Orange Juice")
    assert items == ["Meal: Chicken Burger", "Drink: Orange Juice"]


def test_parse_request_line_items_handles_empty_message():
    assert hotel_app.parse_request_line_items("") == []


def test_submission_assigns_sequential_ticket_numbers(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")

    r1 = client.post(
        "/requests",
        data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"},
        follow_redirects=False,
    )
    r2 = client.post(
        "/requests",
        data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"},
        follow_redirects=False,
    )

    requests_list = repository.get_user_requests("user")
    assert requests_list[0]["queue_number"] == 1
    assert requests_list[0]["queue_ticket"] == "#001"
    assert requests_list[1]["queue_number"] == 2
    assert requests_list[1]["queue_ticket"] == "#002"

    # Redirect passes the request id (not the queue number) as ?ticket=
    assert f"ticket={requests_list[0]['id']}" in r1.headers["Location"]
    assert f"ticket={requests_list[1]['id']}" in r2.headers["Location"]


def test_cancelled_ticket_number_is_never_reused_end_to_end(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")

    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})
    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})

    first_id = repository.get_user_requests("user")[0]["id"]
    client.get(f"/requests/cancel/{first_id}")

    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})

    requests_list = repository.get_user_requests("user")
    assert requests_list[0]["queue_number"] == 1
    assert requests_list[0]["status"] == "Cancelled"
    assert requests_list[2]["queue_number"] == 3


def test_receipt_renders_after_submission_with_ticket_and_items(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    response = client.post(
        "/requests",
        data={"room_number": "12", "request_type": "Toiletries", "toiletry_toothbrush": "2", "toiletry_shampoo": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Request Received" in response.data
    assert b"#001" in response.data
    assert b"Toothbrush x2" in response.data
    assert b"Shampoo x1" in response.data


def test_receipt_not_shown_without_a_ticket_query_param(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})

    response = client.get("/requests")

    assert b"Request Received" not in response.data


def test_user_cannot_view_another_users_receipt_via_ticket_param(client):
    make_user("user2", password="user2pass")
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")
    make_booking(username="user2", room_number="3", room_type="Double", guest_name="Mad Mad", status="Checked In")

    client.post("/login", data={"username": "user", "password": "user123"})
    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})
    victim_request_id = repository.get_user_requests("user")[0]["id"]
    client.get("/logout")

    client.post("/login", data={"username": "user2", "password": "user2pass"})
    response = client.get(f"/requests?ticket={victim_request_id}")

    assert response.status_code == 200
    assert b"Request Received" not in response.data


def test_admin_view_shows_queue_number_and_priority_queue_position_independently(client):
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    client.post(
        "/requests",
        data={"room_number": "12", "request_type": "Repair", "repair_equipment": "Air Conditioner", "repair_issue": "no power"},
    )
    client.get("/logout")

    login_as(client, "admin", "admin123")
    response = client.get("/requests")

    assert b"Queue No.:</strong> #001" in response.data
    assert b"Queue Position:</strong> #1" in response.data


def test_get_display_status_covers_pending_completed_cancelled():
    assert hotel_app.get_display_status({"status": "Pending"}) == "Pending"
    assert hotel_app.get_display_status({"status": "Cancelled"}) == "Cancelled"
    # Accepting a request marks it Completed immediately - there is no
    # separate Ongoing stage, regardless of the guest's "received" flag.
    assert hotel_app.get_display_status({"status": "Accepted"}) == "Completed"
    assert hotel_app.get_display_status({"status": "Accepted", "received": "Yes"}) == "Completed"


def test_guest_side_filter_status_param_has_no_effect(client):
    # The status filter is admin-only; a guest manually appending
    # ?filter_status= must still see their full request list.
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})
    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})

    cancelled_id = repository.get_user_requests("user")[1]["id"]
    client.get(f"/requests/cancel/{cancelled_id}")

    response = client.get("/requests?filter_status=Cancelled")

    assert response.status_code == 200
    assert response.data.count(b"Status:") == 2


def test_admin_can_filter_by_completed_and_accept_marks_it_completed(client):
    make_request(username="user", status="Pending", message="Toiletries: Soap x1", priority="Low", category="Toiletries")
    make_request(username="user", status="Accepted", message="Toiletries: Soap x1", priority="Low", category="Toiletries")
    make_request(username="user", status="Accepted", received=True, message="Toiletries: Soap x1", priority="Low", category="Toiletries")

    login_as(client, "admin", "admin123")

    # Both an accepted-but-not-received and an accepted-and-received request
    # show as Completed - Accept alone is enough, no separate Ongoing stage.
    completed = client.get("/requests?filter_status=Completed")
    assert completed.data.count(b"Status:") == 2
    assert b"Completed" in completed.data
    assert b"Ongoing" not in completed.data


def test_admin_filter_bar_stays_visible_when_filter_matches_nothing(client):
    # Regression: the filter form used to live inside the same block as the
    # filtered results, so a filter matching zero requests hid the very
    # controls needed to change or clear it.
    make_booking(username="user", room_number="12", room_type="Single", guest_name="Alex Guest", status="Checked In")

    login_as(client, "user", "user123")
    client.post("/requests", data={"room_number": "12", "request_type": "Toiletries", "toiletry_soap": "1"})
    client.get("/logout")

    login_as(client, "admin", "admin123")
    response = client.get("/requests?filter_status=Completed")

    assert response.status_code == 200
    assert b'name="filter_status"' in response.data
    assert b"No requests match the selected filters" in response.data


def test_admin_sees_plain_empty_state_when_there_are_truly_no_requests(client):
    login_as(client, "admin", "admin123")
    response = client.get("/requests")

    assert response.status_code == 200
    assert b"No requests yet" in response.data
    assert b'name="filter_status"' not in response.data


def test_logged_in_customer_can_open_feedback_form(client):
    make_booking(id=1, username="user", guest_name="Alex Guest")

    login_as(client, "user", "user123")
    response = client.get("/feedback")

    assert response.status_code == 200
    assert b"Tell Us About Your Stay" in response.data
    assert b"Rate the room facilities" in response.data


def test_customer_cannot_submit_feedback_for_another_customers_booking(client):
    make_user("other_user")
    make_booking(id=1, username="other_user", guest_name="Alex Guest")

    login_as(client, "user", "user123")
    response = client.post(
        "/feedback",
        data={
            "booking_id": "1",
            "facilities_rating": "5",
            "amenities_rating": "4",
            "comfort_cleanliness_rating": "5",
            "additional_feedback": "Great stay overall.",
        },
    )

    assert response.status_code == 200
    assert b"Please select one of your own bookings" in response.data
    assert repository.get_sorted_feedback() == []


def test_feedback_rejects_ratings_outside_one_to_five(client):
    make_booking(id=1, username="user", guest_name="Alex Guest")

    login_as(client, "user", "user123")
    response = client.post(
        "/feedback",
        data={
            "booking_id": "1",
            "facilities_rating": "0",
            "amenities_rating": "6",
            "comfort_cleanliness_rating": "5",
            "additional_feedback": "Ratings should be rejected.",
        },
    )

    assert response.status_code == 200
    assert b"whole numbers from 1 (lowest) to 5 (highest)" in response.data
    assert repository.get_sorted_feedback() == []


def test_feedback_rejects_non_numeric_ratings(client):
    make_booking(id=1, username="user", guest_name="Alex Guest")

    login_as(client, "user", "user123")
    response = client.post(
        "/feedback",
        data={
            "booking_id": "1",
            "facilities_rating": "five",
            "amenities_rating": "4",
            "comfort_cleanliness_rating": "abc",
            "additional_feedback": "Non-numeric ratings should be rejected.",
        },
    )

    assert response.status_code == 200
    assert b"whole numbers from 1 (lowest) to 5 (highest)" in response.data
    assert repository.get_sorted_feedback() == []


def test_valid_feedback_submission_is_stored_with_booking_details_and_timestamp(client):
    make_booking(id=1, username="user", guest_name="Alex Guest")

    login_as(client, "user", "user123")
    response = client.post(
        "/feedback",
        data={
            "booking_id": "1",
            "facilities_rating": "5",
            "amenities_rating": "4",
            "comfort_cleanliness_rating": "3",
            "additional_feedback": "  Quiet room and friendly staff.  ",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/feedback/1" in response.headers.get("Location", "")

    confirm = client.get(response.headers["Location"])
    assert confirm.status_code == 200
    assert b"Your feedback has been submitted successfully" in confirm.data

    all_feedback = repository.get_sorted_feedback()
    assert len(all_feedback) == 1

    entry = all_feedback[0]
    assert entry["booking_id"] == 1
    assert entry["username"] == "user"
    assert entry["guest_name"] == "Alex Guest"
    assert entry["room_number"] == "12"
    assert entry["room_type"] == "Single"
    assert entry["checkin_date"] == "2026-07-01"
    assert entry["checkout_date"] == "2026-07-03"
    assert entry["facilities_rating"] == 5
    assert entry["amenities_rating"] == 4
    assert entry["comfort_cleanliness_rating"] == 3
    assert entry["additional_feedback"] == "Quiet room and friendly staff."
    assert "submitted_at" in entry


def test_feedback_persists_after_data_reload():
    # Replaces the old JSON round-trip test — "persists after reload" is now
    # proven by expiring SQLAlchemy's identity map and re-querying MySQL.
    make_booking(id=1, username="user")
    make_feedback(booking_id=1, additional_feedback="Persisted feedback")

    db.session.expire_all()

    all_feedback = repository.get_sorted_feedback()
    assert len(all_feedback) == 1
    assert all_feedback[0]["additional_feedback"] == "Persisted feedback"


def test_duplicate_feedback_for_same_booking_is_rejected(client):
    make_booking(id=1, username="user", guest_name="Alex Guest")
    make_feedback(booking_id=1, additional_feedback="Already submitted")

    login_as(client, "user", "user123")
    response = client.post(
        "/feedback",
        data={
            "booking_id": "1",
            "facilities_rating": "4",
            "amenities_rating": "4",
            "comfort_cleanliness_rating": "4",
            "additional_feedback": "Trying to submit again.",
        },
    )

    assert response.status_code == 200
    assert b"Feedback has already been submitted for this booking" in response.data
    assert len(repository.get_sorted_feedback()) == 1


def test_normal_customer_cannot_access_admin_feedback_page(client):
    login_as(client, "user", "user123")
    response = client.get("/admin/feedback", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_admin_can_view_all_submitted_feedback(client):
    make_booking(id=1, username="user")
    make_booking(id=2, username="user")
    make_feedback(
        id=1, booking_id=1, guest_name="Older Guest", room_number=12, room_type="Single",
        checkin_date="2026-07-01", checkout_date="2026-07-03",
        additional_feedback="Older submission", submitted_at=datetime(2026, 7, 20, 8, 0, 0),
    )
    make_feedback(
        id=2, booking_id=2, guest_name="Newer Guest", room_number=23, room_type="Double",
        checkin_date="2026-07-10", checkout_date="2026-07-12",
        additional_feedback="Newest submission", submitted_at=datetime(2026, 7, 28, 12, 0, 0),
    )

    login_as(client, "admin", "admin123")
    response = client.get("/admin/feedback")

    assert response.status_code == 200
    assert b"Newer Guest" in response.data
    assert b"Older Guest" in response.data
    assert b"Newest submission" in response.data
    # Newest first: Newer Guest appears before Older Guest
    assert response.data.find(b"Newer Guest") < response.data.find(b"Older Guest")


def test_parse_rating_helper_accepts_only_whole_numbers_one_to_five():
    assert hotel_app.parse_rating("3") == 3
    assert hotel_app.parse_rating("1") == 1
    assert hotel_app.parse_rating("5") == 5
    assert hotel_app.parse_rating("0") is None
    assert hotel_app.parse_rating("6") is None
    assert hotel_app.parse_rating("abc") is None
    assert hotel_app.parse_rating("") is None


def test_logged_in_customer_can_view_own_submitted_feedback(client):
    make_booking(id=1, username="user")
    make_feedback(booking_id=1)

    login_as(client, "user", "user123")
    response = client.get("/feedback/1")

    assert response.status_code == 200
    assert b"Alex Guest" in response.data
    assert b"12" in response.data
    assert b"5 out of 5" in response.data
    assert b"4 out of 5" in response.data
    assert b"3 out of 5" in response.data
    assert b"Quiet room and friendly staff." in response.data


def test_customer_cannot_view_another_customers_feedback(client):
    make_user("other_user")
    make_booking(id=1, username="user")
    make_booking(id=2, username="other_user", guest_name="Other Guest")
    make_feedback(id=1, booking_id=1)
    make_feedback(
        id=2, booking_id=2, username="other_user", guest_name="Other Guest", room_number=23,
        additional_feedback="Secret other feedback", submitted_at=datetime(2026, 7, 28, 11, 0, 0),
    )

    login_as(client, "user", "user123")
    response = client.get("/feedback/2", follow_redirects=False)

    assert response.status_code == 302
    assert "/my-feedback" in response.headers.get("Location", "")

    redirected = client.get("/feedback/2", follow_redirects=True)
    assert b"Secret other feedback" not in redirected.data
    assert b"Other Guest" not in redirected.data


def test_logged_out_visitor_cannot_access_submitted_feedback(client):
    make_booking(id=1, username="user")
    make_feedback(booking_id=1)

    response = client.get("/feedback/1", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")

    list_response = client.get("/my-feedback", follow_redirects=False)
    assert list_response.status_code == 302
    assert "/login" in list_response.headers.get("Location", "")


def test_customer_with_no_feedback_sees_empty_state(client):
    make_booking(id=1, username="user")

    login_as(client, "user", "user123")
    response = client.get("/my-feedback")

    assert response.status_code == 200
    assert b"You have not submitted any feedback yet." in response.data
    assert b"Go to Feedback Form" in response.data


def test_submitted_feedback_remains_visible_after_data_reload(client):
    make_booking(id=1, username="user")
    make_feedback(booking_id=1, additional_feedback="Still visible after reload")

    db.session.expire_all()

    login_as(client, "user", "user123")
    response = client.get("/feedback/1")

    assert response.status_code == 200
    assert b"Still visible after reload" in response.data
    assert b"Alex Guest" in response.data


def test_my_feedback_lists_newest_first(client):
    make_booking(id=1, username="user")
    make_booking(id=2, username="user", guest_name="Newer Guest", room_number="23")
    make_feedback(id=1, booking_id=1, guest_name="Older Guest", additional_feedback="Older submission", submitted_at=datetime(2026, 7, 20, 8, 0, 0))
    make_feedback(id=2, booking_id=2, guest_name="Newer Guest", room_number=23, additional_feedback="Newest submission", submitted_at=datetime(2026, 7, 28, 12, 0, 0))

    login_as(client, "user", "user123")
    response = client.get("/my-feedback")

    assert response.status_code == 200
    assert response.data.find(b"Newer Guest") < response.data.find(b"Older Guest")
    assert b"Newest submission" in response.data
    assert b"Older submission" in response.data


def test_feedback_submission_redirects_to_confirmation_page(client):
    make_booking(id=1, username="user", guest_name="Alex Guest")

    login_as(client, "user", "user123")
    response = client.post(
        "/feedback",
        data={
            "booking_id": "1",
            "facilities_rating": "5",
            "amenities_rating": "4",
            "comfort_cleanliness_rating": "3",
            "additional_feedback": "Redirect confirmation check.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Thank you." in response.data
    assert b"Your feedback has been submitted successfully" in response.data
    assert b"Alex Guest" in response.data
    assert b"Redirect confirmation check." in response.data
    assert b"Return to Guest Dashboard" in response.data
    assert b"View All My Feedback" in response.data
    assert b"5 out of 5" in response.data
    assert b"4 out of 5" in response.data
    assert b"3 out of 5" in response.data


def test_adjust_user_points_clamps_at_zero_and_logs_ledger_entry():
    entry = repository.adjust_user_points("user", -50, "Correction", "admin")

    assert entry["points"] == -50
    assert repository.get_user("user")["points"] == 0  # clamped, never negative
    adjustments = repository.list_loyalty_adjustments()
    assert len(adjustments) == 1
    assert adjustments[0]["reason"] == "Correction"


def test_admin_points_adjustment_route_applies_and_logs(client):
    login_as(client, "admin", "admin123")
    response = client.post(
        "/admin/points/adjust",
        data={"username": "user", "points": "50", "reason": "Goodwill credit"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert repository.get_user("user")["points"] == 50
    assert len(repository.list_loyalty_adjustments()) == 1


def test_admin_points_log_shows_manual_adjustments(client):
    make_points_adjustment(username="user", admin_username="admin", points=20, reason="Compensation")

    login_as(client, "admin", "admin123")
    response = client.get("/admin/points/adjustments")

    assert response.status_code == 200
    assert b"Compensation" in response.data
