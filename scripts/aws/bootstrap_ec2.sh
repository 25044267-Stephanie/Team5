#!/usr/bin/env bash
# Bootstrap Amazon Linux 2023 for Docker Compose + CloudWatch agent.
#
# WHY: Academy EC2 instances are disposable. This script turns a fresh AL2023
# host into a runnable app host without embedding passwords.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/c270-hotel-management}"
CW_DIR="${APP_DIR}/cloudwatch"
LOG_DIR="${APP_DIR}/logs"
STATE_DIR="${APP_DIR}/state"

echo "==> Updating packages (Amazon Linux 2023 / dnf)..."
sudo dnf -y update
sudo dnf -y install docker jq curl unzip amazon-cloudwatch-agent

# AWS CLI is required for ECR login via the instance role (deploy.sh).
if ! command -v aws >/dev/null 2>&1; then
  echo "==> Installing AWS CLI..."
  sudo dnf -y install awscli || sudo dnf -y install awscli-2 || {
    echo "WARN: aws CLI package not found via dnf; install awscliv2 manually if deploy fails." >&2
  }
fi

echo "==> Enabling Docker..."
sudo systemctl enable --now docker

# Compose plugin: prefer dnf package; fall back to Docker's documented plugin path.
if ! docker compose version >/dev/null 2>&1; then
  echo "==> Installing docker compose plugin..."
  sudo dnf -y install docker-compose-plugin || {
    echo "dnf package missing; installing Compose plugin binary..."
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    COMPOSE_VERSION="${COMPOSE_VERSION:-v2.29.7}"
    sudo curl -fsSL \
      "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  }
fi

echo "==> Adding ec2-user to docker group (re-login required to take effect)..."
sudo usermod -aG docker ec2-user || true

echo "==> Creating application directories under ${APP_DIR}..."
sudo mkdir -p "${APP_DIR}" "${CW_DIR}" "${LOG_DIR}" "${STATE_DIR}"
sudo chown -R ec2-user:ec2-user "${APP_DIR}"

echo "==> CloudWatch agent package present:"
command -v amazon-cloudwatch-agent-ctl

cat <<EOF

============================================================
Bootstrap complete. Next steps (run as ec2-user after re-login):

1. Copy project deploy files into ${APP_DIR}
   (docker-compose.prod.yml, database/, cloudwatch/, scripts/aws/)

2. Create ${APP_DIR}/.env with real secrets (never commit):
   FLASK_SECRET_KEY, MYSQL_*, APP_IMAGE=...:GIT_SHA

3. Ensure this instance has an IAM instance profile with ECR pull +
   CloudWatch write permissions (see docs/aws/iam-policies.md).

4. Configure CloudWatch:
   sudo bash ${APP_DIR}/scripts/aws/configure_cloudwatch.sh

5. Deploy:
   bash ${APP_DIR}/scripts/aws/deploy.sh

Verify:  curl -fsS http://127.0.0.1:5050/healthz
============================================================
EOF
