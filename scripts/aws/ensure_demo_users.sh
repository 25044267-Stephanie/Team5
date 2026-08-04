#!/usr/bin/env bash
# Idempotent admin/steph recovery on EC2. Never prints password values.
# Requires SEED_ADMIN_PASSWORD and SEED_STEPH_PASSWORD in the server .env.
# Never passes SEED_USER_PASSWORD into the container (prevents generic "user").
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/c270-hotel-management}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml}"

cd "${APP_DIR}"
# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

# Hard-block generic user seeding on production paths.
unset SEED_USER_PASSWORD || true

if [ -z "${SEED_ADMIN_PASSWORD:-}" ] || [ -z "${SEED_STEPH_PASSWORD:-}" ]; then
  echo "ERROR: SEED_ADMIN_PASSWORD and SEED_STEPH_PASSWORD must be set in ${ENV_FILE}" >&2
  exit 1
fi

# Prefer host-synced seed script (has --ensure-demo-users) over an older image copy.
if [ -f "${APP_DIR}/scripts/seed_dev_users.py" ]; then
  # shellcheck disable=SC2086
  APP_CID="$(docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} ps -q app)"
  if [ -n "${APP_CID}" ]; then
    docker cp "${APP_DIR}/scripts/seed_dev_users.py" "${APP_CID}:/app/scripts/seed_dev_users.py"
  fi
fi

# shellcheck disable=SC2086
docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} exec -T \
  -e SEED_ADMIN_PASSWORD \
  -e SEED_STEPH_PASSWORD \
  -e SEED_USER_PASSWORD= \
  app python scripts/seed_dev_users.py --ensure-demo-users

echo "==> ensure_demo_users.sh finished (admin/steph only; safe to re-run)."
