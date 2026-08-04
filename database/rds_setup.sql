-- Amazon RDS MySQL setup (run once via a private/bastion connection).
-- Replace placeholders. Never commit real passwords.
-- Do NOT set PubliclyAccessible=true on the RDS instance.
--
-- Placeholders:
--   <RDS_APPLICATION_PASSWORD>
--   <RDS_MIGRATE_PASSWORD>

CREATE DATABASE IF NOT EXISTS hotel_management
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Application user (least privilege for runtime).
CREATE USER IF NOT EXISTS 'hotel_app'@'%' IDENTIFIED BY '<RDS_APPLICATION_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE ON hotel_management.* TO 'hotel_app'@'%';

-- Migration user (schema/import only — not used by Flask).
CREATE USER IF NOT EXISTS 'hotel_migrate'@'%' IDENTIFIED BY '<RDS_MIGRATE_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP
  ON hotel_management.* TO 'hotel_migrate'@'%';

FLUSH PRIVILEGES;

-- Next: as hotel_migrate, apply schema via scripts/init_db.py from a trusted host,
-- or import a mysqldump. Then point EC2 app .env MYSQL_USER=hotel_app.
