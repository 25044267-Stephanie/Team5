-- =============================================================================
-- LOCAL MySQL setup for C270 Hotel Management (Workbench / MySQL 8.x)
-- =============================================================================
-- Development schema (exact Workbench name):
--   c270_hotel_management_local
-- Test schema:
--   c270_hotel_management_test
--
-- Run as root in an UNSAVED Workbench query tab.
-- Replace <NEW_HOTEL_APP_PASSWORD> only in that temporary tab, then close
-- without saving. Never put root password or real app passwords in this file.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1) Local development database (exact name)
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS c270_hotel_management_local
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 2) Local test database (pytest)
-- ---------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS c270_hotel_management_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 3) Restricted application user (hotel_app) — NOT root
-- ---------------------------------------------------------------------------
CREATE USER IF NOT EXISTS 'hotel_app'@'localhost'
  IDENTIFIED BY '<NEW_HOTEL_APP_PASSWORD>';
CREATE USER IF NOT EXISTS 'hotel_app'@'127.0.0.1'
  IDENTIFIED BY '<NEW_HOTEL_APP_PASSWORD>';

-- Optional password refresh (run only in an unsaved tab if needed):
-- ALTER USER 'hotel_app'@'localhost' IDENTIFIED BY '<NEW_HOTEL_APP_PASSWORD>';
-- ALTER USER 'hotel_app'@'127.0.0.1' IDENTIFIED BY '<NEW_HOTEL_APP_PASSWORD>';

-- ---------------------------------------------------------------------------
-- 4) Privileges — only the two local schemas
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
  ON c270_hotel_management_local.* TO 'hotel_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
  ON c270_hotel_management_local.* TO 'hotel_app'@'127.0.0.1';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES, DROP
  ON c270_hotel_management_test.* TO 'hotel_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES, DROP
  ON c270_hotel_management_test.* TO 'hotel_app'@'127.0.0.1';

FLUSH PRIVILEGES;

-- ---------------------------------------------------------------------------
-- 5–6) Verification
-- ---------------------------------------------------------------------------
SHOW DATABASES LIKE 'c270_hotel_management%';

SELECT User, Host
FROM mysql.user
WHERE User = 'hotel_app';

SHOW GRANTS FOR 'hotel_app'@'localhost';
SHOW GRANTS FOR 'hotel_app'@'127.0.0.1';
