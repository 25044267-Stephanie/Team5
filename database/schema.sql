-- hotel_management database schema (MySQL 8, InnoDB)
--
-- Mirrors the data model the Flask app (app.py) keeps in MySQL:
-- users, rooms, bookings, feedback, reservation_requests and
-- loyalty_points.
--
-- WARNING: This file DROP TABLEs every application table before recreating
-- them. It is ONLY safe as a first-time bootstrap (e.g. Compose mounts it
-- into /docker-entrypoint-initdb.d/ on an empty volume). Never run it
-- against a populated database or RDS. For idempotent "ensure tables exist"
-- use: python scripts/init_db.py
--
-- Usage (PowerShell, mysql client on PATH):
--   Get-Content database\schema.sql | mysql -u root -p
--
-- This targets the "hotel_management" database by name. To build the test
-- database (hotel_management_test) instead, either run this same file after
-- changing the CREATE DATABASE/USE lines below, or use
-- `python scripts\init_db.py` which builds whichever database is configured
-- in your active .env (MYSQL_DATABASE or MYSQL_TEST_DATABASE) from the
-- SQLAlchemy models directly, without touching this file.

CREATE DATABASE IF NOT EXISTS hotel_management
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE hotel_management;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS loyalty_points;
DROP TABLE IF EXISTS reservation_requests;
DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            ENUM('admin', 'user') NOT NULL DEFAULT 'user',
    points          INT NOT NULL DEFAULT 0,
    last_seen_tier  VARCHAR(20) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- rooms
-- ---------------------------------------------------------------------
CREATE TABLE rooms (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    room_number     INT NOT NULL UNIQUE CHECK (room_number BETWEEN 1 AND 50),
    room_type       ENUM('Single', 'Double', 'Suite') NOT NULL,
    price           DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    status          ENUM('Available', 'Booked', 'Occupied', 'Maintenance') NOT NULL DEFAULT 'Available',
    image_url       VARCHAR(255) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rooms_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- bookings
-- ---------------------------------------------------------------------
CREATE TABLE bookings (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    username            VARCHAR(50) NOT NULL,
    guest_first_name    VARCHAR(100) NOT NULL,
    guest_last_name     VARCHAR(100) NOT NULL,
    guest_name          VARCHAR(200) NOT NULL,
    phone_number        VARCHAR(20) NOT NULL,
    email               VARCHAR(255) NOT NULL,
    room_id             INT NULL,
    room_number         INT NOT NULL,
    room_type           VARCHAR(10) NOT NULL,
    price               DECIMAL(10, 2) NOT NULL,
    checkin_date        DATE NOT NULL,
    checkout_date       DATE NOT NULL,
    status              ENUM('Booked', 'Checked In', 'Checked Out', 'Cancelled', 'No-Show') NOT NULL DEFAULT 'Booked',
    points_redeemed     INT NOT NULL DEFAULT 0,
    points_discount     DECIMAL(10, 2) NOT NULL DEFAULT 0,
    total_price         DECIMAL(10, 2) NOT NULL,
    points_awarded      BOOLEAN NOT NULL DEFAULT FALSE,
    points_earned       INT NOT NULL DEFAULT 0,
    points_base         INT NULL,
    points_tier         VARCHAR(20) NULL,
    points_earned_seen  BOOLEAN NOT NULL DEFAULT FALSE,
    archived            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checked_out_at      DATETIME NULL,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (checkout_date > checkin_date),
    CONSTRAINT fk_bookings_username FOREIGN KEY (username) REFERENCES users(username)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_bookings_room FOREIGN KEY (room_id) REFERENCES rooms(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_bookings_username (username),
    INDEX idx_bookings_room_id (room_id),
    INDEX idx_bookings_status (status),
    INDEX idx_bookings_dates (checkin_date, checkout_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- feedback
-- ---------------------------------------------------------------------
CREATE TABLE feedback (
    id                          INT AUTO_INCREMENT PRIMARY KEY,
    booking_id                  INT NOT NULL UNIQUE,
    username                    VARCHAR(50) NOT NULL,
    guest_name                  VARCHAR(200) NOT NULL,
    room_number                 INT NOT NULL,
    room_type                   VARCHAR(10) NOT NULL,
    checkin_date                DATE NOT NULL,
    checkout_date               DATE NOT NULL,
    facilities_rating           TINYINT NOT NULL CHECK (facilities_rating BETWEEN 1 AND 5),
    amenities_rating            TINYINT NOT NULL CHECK (amenities_rating BETWEEN 1 AND 5),
    comfort_cleanliness_rating  TINYINT NOT NULL CHECK (comfort_cleanliness_rating BETWEEN 1 AND 5),
    additional_feedback         VARCHAR(1000) NOT NULL,
    submitted_at                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_feedback_booking FOREIGN KEY (booking_id) REFERENCES bookings(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_feedback_username FOREIGN KEY (username) REFERENCES users(username)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_feedback_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- reservation_requests (guest in-stay service requests)
-- ---------------------------------------------------------------------
CREATE TABLE reservation_requests (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50) NOT NULL,
    room_number     INT NOT NULL,
    room_type       VARCHAR(10) NOT NULL,
    category        VARCHAR(30) NOT NULL,
    message         VARCHAR(1000) NOT NULL,
    guest_name      VARCHAR(200) NOT NULL,
    priority        ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Low',
    estimated_time  VARCHAR(100) NULL,
    estimated_min   INT NULL,
    estimated_max   INT NULL,
    queue_ticket    VARCHAR(10) NULL,
    status          ENUM('Pending', 'Accepted', 'Cancelled') NOT NULL DEFAULT 'Pending',
    received        BOOLEAN NOT NULL DEFAULT FALSE,
    cancelled_by    VARCHAR(50) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_requests_username FOREIGN KEY (username) REFERENCES users(username)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_requests_username (username),
    INDEX idx_requests_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- loyalty_points (audit ledger backing each user's points balance)
-- ---------------------------------------------------------------------
CREATE TABLE loyalty_points (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    username          VARCHAR(50) NOT NULL,
    admin_username    VARCHAR(50) NOT NULL,
    points            INT NOT NULL,
    reason            VARCHAR(500) NOT NULL,
    is_expiry         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_loyalty_username FOREIGN KEY (username) REFERENCES users(username)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_loyalty_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
