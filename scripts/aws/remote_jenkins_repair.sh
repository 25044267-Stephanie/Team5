#!/usr/bin/env bash
# Idempotent Jenkins host repair after Learner Lab restart. No credentials.
set -euo pipefail

if [[ -f /tmp/bootstrap_jenkins.sh ]]; then
  sudo bash /tmp/bootstrap_jenkins.sh
fi

# Ensure docker compose plugin for Jenkins Validate Workspace
if ! sudo -u jenkins docker compose version >/dev/null 2>&1; then
  sudo mkdir -p /usr/libexec/docker/cli-plugins
  curl -fsSL https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64 -o /tmp/docker-compose
  sudo install -m 0755 /tmp/docker-compose /usr/libexec/docker/cli-plugins/docker-compose
fi

# Bind large /tmp if still tiny tmpfs (Jenkins FreeTempSpace needs ~1GiB)
AVAIL_G=$(df -BG /tmp | awk 'NR==2{gsub(/G/,"",$4); print $4}')
if [[ "${AVAIL_G:-0}" -lt 2 ]]; then
  sudo mkdir -p /var/bigtmp
  sudo chmod 1777 /var/bigtmp
  if ! grep -q '/var/bigtmp' /etc/fstab 2>/dev/null; then
    echo '/var/bigtmp /tmp none bind 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
  sudo mount --bind /var/bigtmp /tmp 2>/dev/null || sudo mount -a || true
  sudo chmod 1777 /tmp
fi

sudo systemctl enable --now docker
sudo systemctl enable jenkins
sudo usermod -aG docker jenkins || true
sudo systemctl restart jenkins
sleep 20

echo "JENKINS_ACTIVE=$(systemctl is-active jenkins)"
echo "DOCKER_ACTIVE=$(systemctl is-active docker)"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8080/login || echo 000)
echo "INTERNAL_HTTP=$CODE"
sudo -u jenkins docker compose version | head -1 | sed 's/^/COMPOSE=/'
df -h /tmp | awk 'NR==2{print "TMP_DF="$0}'
if ROLE_ARN=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null); then
  echo "INSTANCE_ROLE_ARN=${ROLE_ARN}"
else
  echo INSTANCE_ROLE_ARN=unavailable
fi
