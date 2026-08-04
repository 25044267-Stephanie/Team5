# C270 Hotel Management

Flask hotel management app, backed by **MySQL** (via Flask-SQLAlchemy +
PyMySQL). `data.json` is kept in the repo only as a legacy, pre-migration
backup — the running application no longer reads or writes it.

## Team Contributions

Contribution mapping from the project presentation (accurate record for FA
individual scoring — not padded).

### Stephanie Ong — Member 1 — 50%
- Main project integration.
- Login and role-based portal.
- Special-request functionality.
- Testing and final UI debugging.
- DevOps / CI foundation for the FA demonstration path.

### AhmadAkmalRP — Member 2 — 30%
- Room catalogue.
- Room add, edit, and delete functionality.
- Admin room-management pages.
- Room images.
- Booking-form support.
- Room availability and booking-validation support.

### 25043549-Daniel — Member 3 — 15%
- Booking list and booking management.
- Check-in and check-out workflow.
- Booking and room-status updates.
- Guest/admin booking visibility.
- Selected automated test cases related to the booking workflow.

See also `docs/ownership.md`.

## 1. Requirements

- Python 3.11+
- A running MySQL server (8.0+) you can create databases/users on. On
  Windows this is commonly the **MySQL Installer** / **XAMPP** MySQL
  service; on the command line it's whatever `mysql` client ships with it.

## 2. Install Python dependencies

Runtime (matches the Docker image):

```powershell
pip install -r requirements.txt
```

Local development and tests (includes pytest):

```powershell
pip install -r requirements-dev.txt
```

Versions are fully pinned. `requirements.txt` is runtime-only so the
production image does not ship test tooling.

## 3. Create the MySQL user and databases

Two databases are used: `hotel_management` (normal app data) and
`hotel_management_test` (used only by the automated tests, safe to wipe at
any time). Run this once, from any MySQL client connected as an account
that can create users/databases (e.g. `root`):

```sql
CREATE DATABASE IF NOT EXISTS hotel_management       CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS hotel_management_test  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'hotel_app'@'localhost' IDENTIFIED BY 'choose-a-password-here';
GRANT ALL PRIVILEGES ON hotel_management.*      TO 'hotel_app'@'localhost';
GRANT ALL PRIVILEGES ON hotel_management_test.* TO 'hotel_app'@'localhost';
FLUSH PRIVILEGES;
```

## 4. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and fill in real values:

| Variable | Meaning |
|---|---|
| `FLASK_SECRET_KEY` | Flask session secret — any random string |
| `MYSQL_HOST` / `MYSQL_PORT` | Where MySQL is running (usually `localhost` / `3306`) |
| `MYSQL_USER` / `MYSQL_PASSWORD` | The `hotel_app` credentials created in step 3 |
| `MYSQL_DATABASE` | `hotel_management` |
| `MYSQL_TEST_DATABASE` | `hotel_management_test` — only used when running `pytest` |
| `SEED_ADMIN_PASSWORD` / `SEED_USER_PASSWORD` | Passwords for the two dev demo accounts created by `scripts/seed_dev_users.py` (defaults shown in `.env.example` match the old hardcoded `admin123`/`user123`) |

`.env` is gitignored and must never be committed — `.env.example` holds
placeholders only.

## 5. Initialize the schema

Either run the SQL file directly:

```powershell
Get-Content database\schema.sql | mysql -u root -p
```

...or let SQLAlchemy build the tables from the models (equivalent, and
also what you'd use to build the *test* database):

```powershell
python scripts\init_db.py          # builds MYSQL_DATABASE
python scripts\init_db.py --test   # builds MYSQL_TEST_DATABASE
```

Both are safe to re-run.

## 6. Migrate existing data.json (optional, one-time)

If you have an existing `data.json` with real data in it:

```powershell
python scripts\migrate_json_to_mysql.py
```

This seeds the two default accounts (admin/user) if missing, then migrates
`data.json`'s rooms, bookings, users, feedback, and loyalty-point
adjustments into MySQL, in that order. It's idempotent (safe to re-run —
already-migrated rows are skipped, never duplicated), validates every
record and prints exactly what it skipped and why, and never touches or
deletes `data.json` itself.

Reservation requests (`reservation_requests` table) are not part of this
migration: the old JSON-based app never actually persisted them (they only
ever lived in memory and were lost on every restart), so there is nothing
to bring over — new requests submitted after the migration start
persisting normally.

## 7. Run the application

```powershell
python app.py
```

Open `http://127.0.0.1:5050` (the app listens on **port 5050**, not
Flask's default 5000).

Default accounts (created by `scripts/seed_dev_users.py`, or already
present if you migrated an existing `data.json`):

- Admin — username: `admin`, password: `admin123` (or your `SEED_ADMIN_PASSWORD`)
- Guest — username: `user`, password: `user123` (or your `SEED_USER_PASSWORD`)

### Verifying the app is actually connected to MySQL

- The app fails fast at startup with a clear `Configuration error` if any
  required `.env` variable is missing — if it starts at all, it has valid
  MySQL connection settings.
- Log in, create a booking, then check it directly in MySQL:
  ```sql
  SELECT * FROM hotel_management.bookings ORDER BY id DESC LIMIT 1;
  ```
  If your booking shows up there, you're reading/writing MySQL, not a file.

## 8. Run the automated tests

```powershell
pytest
```

Tests run against `MYSQL_TEST_DATABASE` only — `tests/conftest.py` forces
this before the app module is even imported, so a test run can never touch
or erase your `hotel_management` dev database. Every test gets a freshly
truncated database (reseeded with just the two default accounts) so tests
never depend on run order and never leave residue behind.

## 9. Run with Docker

Docker Compose starts both the Flask application and its MySQL database. Copy
the environment template, then set strong values for `FLASK_SECRET_KEY`,
`MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD`:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

`docker-compose.override.yml` is merged automatically for local builds.
Probe readiness at `http://localhost:5050/healthz` (expects JSON
`{"status":"ok","database":"up"}`).

Open `http://localhost:5050`. The database is stored in Docker's named
`mysql-data` volume, so it persists when containers are restarted. The schema
is created automatically only on the first database start. To create the demo
accounts after startup, run:

```powershell
docker compose exec app python scripts/seed_dev_users.py
```

To stop the stack, use `docker compose down`. Do not add `--volumes` unless
you intentionally want to remove the database and all its data.

## 10. CI pipeline (GitHub Actions)

Primary CI is `.github/workflows/ci.yml` (strict gate order):

1. **Lint** — `ruff check`
2. **Test** — all 111 pytest tests against a MySQL 8.4 service container
3. **Build** — Buildx image tagged with the short git SHA (no registry push yet)
4. **Scan** — Trivy fails the job on fixable HIGH/CRITICAL findings

See `docs/phase-2-verify.md` and `docs/verification-phase2.md`. Branch
protection on `main` should require all four job names: `Lint (ruff)`,
`Test (pytest + MySQL 8.4)`, `Build image (Buildx)`, `Scan image (Trivy)`.

### Deploy to AWS (Academy / us-east-1)

After CI succeeds on `main`, `.github/workflows/deploy-aws.yml` pushes the
SHA-tagged image to Amazon ECR and deploys it to EC2 with
`docker-compose.prod.yml` (app + MySQL volume, CloudWatch agent).

Full steps: `docs/aws-deployment.md`  
Demo checklist: `docs/fa-demonstration-checklist.md`  
IAM examples: `docs/aws/iam-policies.md`

### Legacy Jenkins pipeline

`Jenkinsfile` is **legacy** (kept for history). It still describes a Jenkins
Multibranch flow: checkout, pytest against MySQL, build, publish, SSH deploy.

Before running it, configure the Jenkins agent with Docker and Docker Compose,
then:

1. Replace `YOUR_DOCKERHUB_USERNAME` in `Jenkinsfile` with your Docker Hub
   username (or change it to your preferred container registry path).
2. Create a Jenkins **Username with password** credential called
   `dockerhub-credentials`; use a Docker Hub access token as the password.
3. Create an **SSH Username with private key** credential called
   `hotel-production-ssh`.
4. Set `DEPLOY_HOST` as an environment variable for the Jenkins job, containing
   the production server's hostname or IP address.
5. On the production server, install Docker and Compose, clone this repository
   to `/opt/c270-hotel-management`, create its production `.env`, and run
   `docker compose up -d` once to initialize MySQL.

Only commits merged into `main` publish and deploy. The deployment command
pulls the image tagged with the Jenkins build number, so a specific build can
be rolled back by rerunning `IMAGE_NAME=<registry-image>:<old-build-number>
docker compose up -d app` on the server.

## Room rules

- Rooms 2-40 (even): Single, $100 per night
- Rooms 1-39 (odd): Double, $200 per night
- Rooms 41-50: Suite, $500 per night
- The starting catalogue contains 25 room numbers selected from 1-50.
- Duplicate room numbers and room numbers outside 1-50 are rejected.
