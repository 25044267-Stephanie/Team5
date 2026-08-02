#!/usr/bin/env bash
# Update production .env demo seed entries only (admin/steph).
# Removes SEED_USER_PASSWORD so generic "user" is never created on deploy.
# Never prints password values. Requires SEED_ADMIN_PASSWORD and SEED_STEPH_PASSWORD in env.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/c270-hotel-management}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"

if [ -z "${SEED_ADMIN_PASSWORD:-}" ] || [ -z "${SEED_STEPH_PASSWORD:-}" ]; then
  echo "ERROR: SEED_ADMIN_PASSWORD and SEED_STEPH_PASSWORD must be set in the environment" >&2
  exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
  echo "ERROR: missing ${ENV_FILE}" >&2
  exit 1
fi

export ENV_FILE
export SEED_ADMIN_PASSWORD
export SEED_STEPH_PASSWORD

python3 - <<'PY'
from pathlib import Path
import os

path = Path(os.environ["ENV_FILE"])
lines = []
seen_admin = seen_steph = False
for line in path.read_text(encoding="utf-8").splitlines(True):
    if line.startswith("SEED_USER_PASSWORD="):
        continue
    if line.startswith("SEED_ADMIN_PASSWORD="):
        lines.append("SEED_ADMIN_PASSWORD=" + os.environ["SEED_ADMIN_PASSWORD"] + "\n")
        seen_admin = True
        continue
    if line.startswith("SEED_STEPH_PASSWORD="):
        lines.append("SEED_STEPH_PASSWORD=" + os.environ["SEED_STEPH_PASSWORD"] + "\n")
        seen_steph = True
        continue
    lines.append(line if line.endswith("\n") else line + "\n")
if not seen_admin:
    lines.append("SEED_ADMIN_PASSWORD=" + os.environ["SEED_ADMIN_PASSWORD"] + "\n")
if not seen_steph:
    lines.append("SEED_STEPH_PASSWORD=" + os.environ["SEED_STEPH_PASSWORD"] + "\n")
path.write_text("".join(lines), encoding="utf-8")
path.chmod(0o600)
print("SEED_ENV_UPDATED_NO_USER")
PY
