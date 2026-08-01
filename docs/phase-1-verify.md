# Phase 1 verification checklist

Run these on your machine after Phase 1 changes. Expected outputs are exact.

## 0. Fix local MySQL auth (required for pytest)

Your `.env` has `MYSQL_USER=hotel_app` but MySQL rejected the password
(`1045 Access denied`). Align the MySQL user with `.env` (as root):

```sql
CREATE DATABASE IF NOT EXISTS hotel_management CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS hotel_management_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'hotel_app'@'localhost' IDENTIFIED BY 'YOUR_PASSWORD_FROM_ENV';
ALTER USER 'hotel_app'@'localhost' IDENTIFIED BY 'YOUR_PASSWORD_FROM_ENV';
GRANT ALL PRIVILEGES ON hotel_management.* TO 'hotel_app'@'localhost';
GRANT ALL PRIVILEGES ON hotel_management_test.* TO 'hotel_app'@'localhost';
FLUSH PRIVILEGES;
```

Then:

```powershell
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest -q
```

Expected: `111 passed`.

## 1. Install Docker Desktop (required for container gates)

Docker was not on PATH during Phase 1. Install Docker Desktop for Windows,
restart the terminal, confirm:

```powershell
docker version
docker compose version
```

## 2. Compose up + healthz

```powershell
docker compose up --build -d
curl http://localhost:5050/healthz
```

Expected JSON body: `{"status":"ok","database":"up"}` and HTTP 200.

## 3. Non-root user

```powershell
docker compose exec app whoami
```

Expected: `app` (not `root`).

## 4. Image size (before/after)

Before Phase 1 there was no local image on this machine. After build:

```powershell
docker images c270-hotel-management:local
```

Record the SIZE column for the demo notes / CHANGELOG.

## 5. Optional: stop stack

```powershell
docker compose down
```

Do **not** add `--volumes` unless you intend to wipe the DB volume.
