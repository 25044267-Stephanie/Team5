from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _iso(value):
    return value.isoformat() if value is not None else None


def _date(value):
    return value.strftime("%Y-%m-%d") if value is not None else None


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "user", name="user_role"), nullable=False, default="user")
    points = db.Column(db.Integer, nullable=False, default=0)
    last_seen_tier = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    def to_dict(self):
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role,
            "points": self.points,
            "last_seen_tier": self.last_seen_tier,
        }


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.Integer, unique=True, nullable=False)
    room_type = db.Column(db.Enum("Single", "Double", "Suite", name="room_type"), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(
        db.Enum("Available", "Booked", "Occupied", "Maintenance", name="room_status"),
        nullable=False,
        default="Available",
    )
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    __table_args__ = (db.Index("idx_rooms_status", "status"),)

    def to_dict(self):
        return {
            "id": self.id,
            "room_number": str(self.room_number),
            "type": self.room_type,
            "price": float(self.price),
            "status": self.status,
            "image": self.image_url,
        }


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), db.ForeignKey("users.username", onupdate="CASCADE"), nullable=False)
    guest_first_name = db.Column(db.String(100), nullable=False)
    guest_last_name = db.Column(db.String(100), nullable=False)
    guest_name = db.Column(db.String(200), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    room_number = db.Column(db.Integer, nullable=False)
    room_type = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    checkin_date = db.Column(db.Date, nullable=False)
    checkout_date = db.Column(db.Date, nullable=False)
    status = db.Column(
        db.Enum("Booked", "Checked In", "Checked Out", "Cancelled", "No-Show", name="booking_status"),
        nullable=False,
        default="Booked",
    )
    points_redeemed = db.Column(db.Integer, nullable=False, default=0)
    points_discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    points_awarded = db.Column(db.Boolean, nullable=False, default=False)
    points_earned = db.Column(db.Integer, nullable=False, default=0)
    points_base = db.Column(db.Integer, nullable=True)
    points_tier = db.Column(db.String(20), nullable=True)
    points_earned_seen = db.Column(db.Boolean, nullable=False, default=False)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    checked_out_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.Index("idx_bookings_status", "status"),
        db.Index("idx_bookings_dates", "checkin_date", "checkout_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "guest_name": self.guest_name,
            "guest_first_name": self.guest_first_name,
            "guest_last_name": self.guest_last_name,
            "phone_number": self.phone_number,
            "email": self.email,
            "room_id": self.room_id,
            "room_number": str(self.room_number),
            "room_type": self.room_type,
            "price": float(self.price),
            "checkin_date": _date(self.checkin_date),
            "checkout_date": _date(self.checkout_date),
            "status": self.status,
            "points_redeemed": self.points_redeemed,
            "points_discount": float(self.points_discount),
            "total_price": float(self.total_price),
            "points_awarded": self.points_awarded,
            "points_earned": self.points_earned,
            "points_base": self.points_base,
            "points_tier": self.points_tier,
            "points_earned_seen": self.points_earned_seen,
            "archived": self.archived,
            "created_at": _iso(self.created_at),
            "checked_out_at": _iso(self.checked_out_at),
        }


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    username = db.Column(db.String(50), db.ForeignKey("users.username", onupdate="CASCADE"), nullable=False)
    guest_name = db.Column(db.String(200), nullable=False)
    room_number = db.Column(db.Integer, nullable=False)
    room_type = db.Column(db.String(10), nullable=False)
    checkin_date = db.Column(db.Date, nullable=False)
    checkout_date = db.Column(db.Date, nullable=False)
    facilities_rating = db.Column(db.SmallInteger, nullable=False)
    amenities_rating = db.Column(db.SmallInteger, nullable=False)
    comfort_cleanliness_rating = db.Column(db.SmallInteger, nullable=False)
    additional_feedback = db.Column(db.String(1000), nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())

    def to_dict(self):
        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "username": self.username,
            "guest_name": self.guest_name,
            "room_number": str(self.room_number),
            "room_type": self.room_type,
            "checkin_date": _date(self.checkin_date),
            "checkout_date": _date(self.checkout_date),
            "facilities_rating": self.facilities_rating,
            "amenities_rating": self.amenities_rating,
            "comfort_cleanliness_rating": self.comfort_cleanliness_rating,
            "additional_feedback": self.additional_feedback,
            "submitted_at": _iso(self.submitted_at),
        }


class ReservationRequest(db.Model):
    __tablename__ = "reservation_requests"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), db.ForeignKey("users.username", onupdate="CASCADE"), nullable=False)
    room_number = db.Column(db.Integer, nullable=False)
    room_type = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    guest_name = db.Column(db.String(200), nullable=False)
    priority = db.Column(db.Enum("Low", "Medium", "High", name="request_priority"), nullable=False, default="Low")
    estimated_time = db.Column(db.String(100), nullable=True)
    estimated_min = db.Column(db.Integer, nullable=True)
    estimated_max = db.Column(db.Integer, nullable=True)
    queue_ticket = db.Column(db.String(10), nullable=True)
    status = db.Column(
        db.Enum("Pending", "Accepted", "Cancelled", name="request_status"), nullable=False, default="Pending"
    )
    received = db.Column(db.Boolean, nullable=False, default=False)
    cancelled_by = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    __table_args__ = (db.Index("idx_requests_status", "status"),)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "room_number": str(self.room_number),
            "room_type": self.room_type,
            "category": self.category,
            "message": self.message,
            "guest_name": self.guest_name,
            "priority": self.priority,
            "created_at": _iso(self.created_at),
            "estimated_time": self.estimated_time,
            "estimated_min": self.estimated_min,
            "estimated_max": self.estimated_max,
            "queue_number": self.id,
            "queue_ticket": self.queue_ticket,
            "status": self.status,
            "received": "Yes" if self.received else None,
            "cancelled_by": self.cancelled_by,
        }


class LoyaltyPoint(db.Model):
    __tablename__ = "loyalty_points"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), db.ForeignKey("users.username", onupdate="CASCADE"), nullable=False)
    admin_username = db.Column(db.String(50), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    is_expiry = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "admin_username": self.admin_username,
            "points": self.points,
            "reason": self.reason,
            "created_at": _iso(self.created_at),
            "is_expiry": self.is_expiry,
        }
