#!/usr/bin/env bash
# Roll back to the previously deployed immutable image tag.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/c270-hotel-management}"
STATE_DIR="${STATE_DIR:-${APP_DIR}/state}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
TARGET_IMAGE="${1:-}"

if [[ -z "${TARGET_IMAGE}" ]]; then
  if [[ ! -f "${STATE_DIR}/previous_image" ]]; then
    echo "ERROR: no previous_image recorded and no image argument given." >&2
    echo "Usage: $0 <ecr-uri:sha>" >&2
    exit 1
  fi
  TARGET_IMAGE="$(cat "${STATE_DIR}/previous_image")"
fi

echo "==> Rolling back to ${TARGET_IMAGE}"

# Update APP_IMAGE in .env without printing secret values.
if grep -q '^APP_IMAGE=' "${ENV_FILE}"; then
  # Use a temp file to avoid sed -i portability issues.
  awk -v img="${TARGET_IMAGE}" '
    BEGIN { done=0 }
    /^APP_IMAGE=/ { print "APP_IMAGE=" img; done=1; next }
    { print }
    END { if (!done) print "APP_IMAGE=" img }
  ' "${ENV_FILE}" > "${ENV_FILE}.tmp"
  mv "${ENV_FILE}.tmp" "${ENV_FILE}"
else
  echo "APP_IMAGE=${TARGET_IMAGE}" >> "${ENV_FILE}"
fi

export APP_IMAGE="${TARGET_IMAGE}"
bash "${APP_DIR}/scripts/aws/deploy.sh"
