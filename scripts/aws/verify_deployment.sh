#!/usr/bin/env bash
# Post-deploy verification: container health + localhost /healthz.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/c270-hotel-management}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5050/healthz}"
TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-60}"

cd "${APP_DIR}"

echo "==> Compose status"
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" ps

echo "==> Waiting for ${HEALTH_URL}"
deadline=$((SECONDS + TIMEOUT_SEC))
ok=0
while (( SECONDS < deadline )); do
  if curl -fsS "${HEALTH_URL}" >/tmp/c270-verify-healthz.json 2>/dev/null \
    && grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' /tmp/c270-verify-healthz.json; then
    ok=1
    break
  fi
  sleep 3
done

if (( ok != 1 )); then
  echo "ERROR: /healthz verification failed" >&2
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" logs --tail=80 app || true
  exit 1
fi

echo "==> Health payload:"
cat /tmp/c270-verify-healthz.json
echo
echo "==> Deployment verification OK"
