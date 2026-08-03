#!/usr/bin/env bash
# Read-only Jenkins host probe. No credentials. Safe to re-run.
set -euo pipefail

echo "JENKINS_ACTIVE=$(systemctl is-active jenkins 2>/dev/null || echo inactive)"
echo "JENKINS_ENABLED=$(systemctl is-enabled jenkins 2>/dev/null || echo disabled)"
echo "DOCKER_ACTIVE=$(systemctl is-active docker 2>/dev/null || echo inactive)"
echo "DOCKER_ENABLED=$(systemctl is-enabled docker 2>/dev/null || echo disabled)"
java -version 2>&1 | head -1 | sed 's/^/JAVA=/'
git --version 2>/dev/null | sed 's/^/GIT=/' || echo GIT=missing
docker --version 2>/dev/null | sed 's/^/DOCKER=/' || echo DOCKER=missing
aws --version 2>/dev/null | sed 's/^/AWS=/' || echo AWS=missing
ansible --version 2>/dev/null | head -1 | sed 's/^/ANSIBLE=/' || echo ANSIBLE=missing
trivy --version 2>/dev/null | head -1 | sed 's/^/TRIVY=/' || echo TRIVY=missing
if sudo -u jenkins docker version >/dev/null 2>&1; then
  echo JENKINS_DOCKER=ok
else
  echo JENKINS_DOCKER=fail
fi
if sudo ss -ltnp 2>/dev/null | grep -E ':8080\b' >/dev/null; then
  echo LISTEN_8080=yes
else
  echo LISTEN_8080=no
fi
CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8080/login || echo 000)
echo "INTERNAL_HTTP=$CODE"
# Instance-role identity (do not use user keys)
if ROLE_ARN=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null); then
  echo "INSTANCE_ROLE_ARN=${ROLE_ARN}"
else
  echo INSTANCE_ROLE_ARN=unavailable
fi
if ! df -h /tmp 2>/dev/null | awk 'NR==2{print $2}' | grep -Eq 'G'; then
  echo TMP_SMALL=yes
else
  echo TMP_SMALL=no
fi
df -h /tmp | awk 'NR==2{print "TMP_DF="$0}'
