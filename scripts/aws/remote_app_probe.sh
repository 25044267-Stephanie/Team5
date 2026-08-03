#!/usr/bin/env bash
# Read-only application host probe. Never deletes volumes or data.
set -euo pipefail

if [[ ! -d /home/ec2-user/c270-hotel-management ]]; then
  echo APP_DIR=missing
  exit 0
fi
cd /home/ec2-user/c270-hotel-management
echo APP_DIR=ok

docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml ps 2>/dev/null | sed 's/^/COMPOSE=/' || true
CODE=$(curl -sS -o /tmp/hz.json -w '%{http_code}' --max-time 8 http://127.0.0.1:5050/healthz || echo 000)
echo "HEALTH_HTTP=$CODE"
head -c 200 /tmp/hz.json 2>/dev/null || true
echo
UID_VAL=$(docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml exec -T app id -u 2>/dev/null || echo unknown)
echo "APP_UID=$UID_VAL"
if ss -lntp 2>/dev/null | grep -q ':3306'; then
  echo MYSQL_HOST_BIND=yes_bad
else
  echo MYSQL_HOST_BIND=no_ok
fi
