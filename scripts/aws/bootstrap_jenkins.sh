#!/usr/bin/env bash
# Idempotent Jenkins CI host bootstrap for Amazon Linux 2023.
# Installs Java 21, Jenkins, Git, Docker, AWS CLI, Python 3, Ansible, Trivy.
# Never stores credentials. Never touches the application EC2 or MySQL.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run as root (sudo bash scripts/aws/bootstrap_jenkins.sh)" >&2
  exit 1
fi

echo "==> Updating DNF metadata..."
dnf -y makecache

echo "==> Installing base packages..."
dnf -y install \
  git \
  python3 \
  python3-pip \
  java-21-amazon-corretto-headless \
  wget \
  curl-minimal \
  tar \
  gzip \
  shadow-utils \
  chkconfig

echo "==> Installing Docker..."
if ! command -v docker >/dev/null 2>&1; then
  dnf -y install docker
fi
systemctl enable --now docker

echo "==> Installing AWS CLI v2 when missing..."
if ! command -v aws >/dev/null 2>&1; then
  cd /tmp
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
  dnf -y install unzip || true
  unzip -qo awscliv2.zip
  ./aws/install --update
  rm -rf aws awscliv2.zip
fi

echo "==> Installing Ansible..."
if ! command -v ansible-playbook >/dev/null 2>&1; then
  python3 -m pip install --upgrade pip
  python3 -m pip install "ansible-core>=2.15,<2.18"
fi

echo "==> Installing Trivy..."
if ! command -v trivy >/dev/null 2>&1; then
  cat >/etc/yum.repos.d/trivy.repo <<'EOF'
[trivy]
name=Trivy repository
baseurl=https://aquasecurity.github.io/trivy-repo/rpm/releases/$basearch/
gpgcheck=0
enabled=1
EOF
  dnf -y install trivy || {
    echo "WARN: dnf trivy install failed; Jenkinsfile falls back to aquasec/trivy Docker image."
  }
fi

echo "==> Installing Jenkins..."
if ! rpm -q jenkins >/dev/null 2>&1; then
  wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
  rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io-2023.key || \
    rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io.key || true
  dnf -y install jenkins
fi

systemctl enable --now jenkins

echo "==> Adding jenkins user to docker group..."
usermod -aG docker jenkins || true
systemctl restart jenkins

echo "==> Waiting for Jenkins HTTP on 8080..."
for i in $(seq 1 60); do
  if curl -fsS -o /dev/null http://127.0.0.1:8080; then
    break
  fi
  # Jenkins may return 403 before setup — port open is enough.
  if ss -lnt | grep -q ':8080'; then
    break
  fi
  sleep 5
done

echo "==> Version evidence (non-secret):"
java -version 2>&1 | head -n 1 || true
jenkins --version 2>/dev/null || rpm -q jenkins || true
git --version
docker --version
aws --version 2>&1 | head -n 1
python3 --version
ansible-playbook --version 2>&1 | head -n 1 || echo "ansible-playbook missing"
trivy --version 2>&1 | head -n 1 || echo "trivy missing (Docker fallback OK)"
id jenkins
groups jenkins || true

echo "==> bootstrap_jenkins.sh finished."
echo "Next: open http://<THIS_HOST_PUBLIC_IP>:8080 and complete the browser setup wizard."
echo "Initial admin password (retrieve via SSH only): sudo cat /var/lib/jenkins/secrets/initialAdminPassword"
