#!/usr/bin/env bash
# Pull the immutable ECR image and deploy with docker-compose.prod.yml.
#
# WHY: Deploy uses the same SHA-tagged image CI built/scanned — never rebuild
# on EC2. Preferred compose file talks to private RDS (no local DB volume).
# Never run: docker compose down --volumes
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/c270-hotel-management}"
# Prefer multi-file Academy fallback when COMPOSE_FILES is set; otherwise a
# single COMPOSE_FILE (RDS prod). Never use: docker compose down --volumes
COMPOSE_FILE="${COMPOSE_FILE:-}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
STATE_DIR="${STATE_DIR:-${APP_DIR}/state}"
LOG_DIR="${LOG_DIR:-${APP_DIR}/logs}"
AWS_REGION="${AWS_REGION:-us-east-1}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5050/healthz}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-120}"
RUN_ROOM_MIGRATE="${RUN_ROOM_MIGRATE:-true}"
RUN_DEMO_USER_ENSURE="${RUN_DEMO_USER_ENSURE:-true}"

cd "${APP_DIR}"

compose() {
  if [[ -n "${COMPOSE_FILE}" ]]; then
    docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"
  else
    # shellcheck disable=SC2086
    docker compose --env-file "${ENV_FILE}" ${COMPOSE_FILES} "$@"
  fi
}

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: missing ${ENV_FILE}" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "${ENV_FILE}"
set +a

if [[ -z "${APP_IMAGE:-}" ]]; then
  echo "ERROR: APP_IMAGE must be set in ${ENV_FILE} (ECR URI:SHA)." >&2
  exit 1
fi

mkdir -p "${STATE_DIR}" "${LOG_DIR}"
PREVIOUS_IMAGE=""
if [[ -f "${STATE_DIR}/current_image" ]]; then
  PREVIOUS_IMAGE="$(cat "${STATE_DIR}/current_image")"
  echo "${PREVIOUS_IMAGE}" > "${STATE_DIR}/previous_image"
  echo "==> Previous image recorded for rollback: ${PREVIOUS_IMAGE}"
fi

if [[ -z "${MYSQL_HOST:-}" ]]; then
  echo "ERROR: MYSQL_HOST must be set (private RDS endpoint, or 'db' for mysql-fallback)." >&2
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

{
  echo "==> $(date -u +%Y-%m-%dT%H:%M:%SZ) deploy start image=${APP_IMAGE} mysql_host=${MYSQL_HOST}"
} | tee -a "${LOG_DIR}/deploy.log"

echo "==> Logging in to ECR ${ECR_REGISTRY} via instance role..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "==> Pulling ${APP_IMAGE}"
docker pull "${APP_IMAGE}"

echo "==> Starting stack..."
compose up -d

echo "==> Waiting for /healthz status=ok (timeout ${HEALTH_TIMEOUT_SEC}s)..."
deadline=$((SECONDS + HEALTH_TIMEOUT_SEC))
healthy=0
while (( SECONDS < deadline )); do
  if curl -fsS "${HEALTH_URL}" >/tmp/c270-healthz.json 2>/dev/null \
    && grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' /tmp/c270-healthz.json; then
    healthy=1
    break
  fi
  sleep 3
done

if (( healthy != 1 )); then
  echo "ERROR: health check timed out or returned non-ok against ${HEALTH_URL}" >&2
  compose ps || true
  compose logs --tail=80 app || true
  exit 1
fi

echo "==> Health response:"
cat /tmp/c270-healthz.json
echo

if [[ "${RUN_ROOM_MIGRATE}" == "true" ]]; then
  echo "==> Idempotent room migrate (missing rooms only)..."
  if [[ -x "${APP_DIR}/scripts/aws/migrate_rooms.sh" ]]; then
    APP_DIR="${APP_DIR}" ENV_FILE="${ENV_FILE}" COMPOSE_FILES="${COMPOSE_FILES}" \
      bash "${APP_DIR}/scripts/aws/migrate_rooms.sh"
  else
    compose exec -T app python scripts/migrate_json_to_mysql.py --rooms-only --verbose || \
      compose --profile migrate run --rm db-migrate
  fi
fi

if [[ "${RUN_DEMO_USER_ENSURE}" == "true" ]]; then
  echo "==> Idempotent demo users (admin/steph only)..."
  # Never create the generic local "user" account on production deploys.
  unset SEED_USER_PASSWORD || true
  if [[ -x "${APP_DIR}/scripts/aws/ensure_demo_users.sh" ]]; then
    APP_DIR="${APP_DIR}" ENV_FILE="${ENV_FILE}" COMPOSE_FILES="${COMPOSE_FILES}" \
      bash "${APP_DIR}/scripts/aws/ensure_demo_users.sh"
  else
    # shellcheck disable=SC1090
    set -a
    # shellcheck disable=SC1091
    source "${ENV_FILE}"
    set +a
    unset SEED_USER_PASSWORD || true
    compose exec -T -e SEED_ADMIN_PASSWORD -e SEED_STEPH_PASSWORD -e SEED_USER_PASSWORD= \
      app python scripts/seed_dev_users.py --ensure-demo-users
  fi
fi

echo "${APP_IMAGE}" > "${STATE_DIR}/current_image"
echo "==> Deploy succeeded: ${APP_IMAGE}"
compose ps
