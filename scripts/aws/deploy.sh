#!/usr/bin/env bash
# Pull the immutable ECR image and deploy with docker-compose.prod.yml.
#
# WHY: Deploy uses the same SHA-tagged image CI built/scanned — never rebuild
# on EC2. MySQL named volume is preserved (never compose down --volumes).
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/c270-hotel-management}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
STATE_DIR="${STATE_DIR:-${APP_DIR}/state}"
AWS_REGION="${AWS_REGION:-us-east-1}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5050/healthz}"
HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-120}"

cd "${APP_DIR}"

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

mkdir -p "${STATE_DIR}"
PREVIOUS_IMAGE=""
if [[ -f "${STATE_DIR}/current_image" ]]; then
  PREVIOUS_IMAGE="$(cat "${STATE_DIR}/current_image")"
  echo "${PREVIOUS_IMAGE}" > "${STATE_DIR}/previous_image"
  echo "==> Previous image recorded for rollback: ${PREVIOUS_IMAGE}"
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Logging in to ECR ${ECR_REGISTRY} via instance role..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "==> Pulling ${APP_IMAGE}"
docker pull "${APP_IMAGE}"

echo "==> Starting stack (preserving volumes)..."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

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
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps || true
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs --tail=80 app || true
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs --tail=40 db || true
  exit 1
fi

echo "==> Health response:"
cat /tmp/c270-healthz.json
echo
echo "${APP_IMAGE}" > "${STATE_DIR}/current_image"
echo "==> Deploy succeeded: ${APP_IMAGE}"
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps
