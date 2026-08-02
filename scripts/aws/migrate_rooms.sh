#!/usr/bin/env bash
# Idempotent room restore on EC2 (Academy MySQL fallback or any Compose stack).
#
# Uses the running/pulled APP_IMAGE which must contain data.json + migrate script.
# Never deletes volumes or tables. Safe to re-run (second run inserts 0 rooms).
#
# Usage on EC2 (from the app directory that holds .env and Compose files):
#   bash scripts/aws/migrate_rooms.sh
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/c270-hotel-management}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
# Academy fallback stack (db + app). Override if using RDS-only prod compose.
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml}"

cd "${APP_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1091
source "${ENV_FILE}"
set +a

if [[ -z "${APP_IMAGE:-}" && -z "${IMAGE_NAME:-}" ]]; then
  echo "ERROR: set APP_IMAGE (or IMAGE_NAME) in ${ENV_FILE}" >&2
  exit 1
fi

echo "==> Waiting for db health..."
# shellcheck disable=SC2086
docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} ps

echo "==> Running idempotent --rooms-only migrate..."
# Prefer the one-shot profile when available; fall back to exec on the app container.
# shellcheck disable=SC2086
if docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} --profile migrate config --services 2>/dev/null | grep -qx db-migrate; then
  # shellcheck disable=SC2086
  docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} --profile migrate run --rm db-migrate
else
  # shellcheck disable=SC2086
  docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} exec -T app \
    python scripts/migrate_json_to_mysql.py --rooms-only --verbose
fi

echo "==> Room count:"
# shellcheck disable=SC2086
docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} exec -T db \
  sh -lc 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) AS room_count FROM rooms;"'

echo "==> migrate_rooms.sh finished (re-run is safe; expect skipped/already present)."
