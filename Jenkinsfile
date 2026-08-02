// C270 Hotel Management — Jenkins Declarative Pipeline (L4)
// Secrets: Jenkins Credentials + EC2 IAM instance profile only.
// Never commit AWS keys, PEM files, DB passwords, or webhook secrets.

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        booleanParam(
            name: 'DEPLOY_TO_AWS',
            defaultValue: false,
            description: 'When true: push immutable image to ECR and deploy via Ansible'
        )
        booleanParam(
            name: 'RUN_SECURITY_SCAN',
            defaultValue: true,
            description: 'Trivy HIGH/CRITICAL gate (recommended true for FA evidence)'
        )
        booleanParam(
            name: 'ROLLBACK_ONLY',
            defaultValue: false,
            description: 'Skip build/push; restore previous app image on EC2 and verify health'
        )
    }

    environment {
        AWS_REGION = 'us-east-1'
        ECR_REPOSITORY = 'c270-hotel-management'
        APP_INSTANCE_NAME = 'c270-hotel-app'
        APP_DIR = '/home/ec2-user/c270-hotel-management'
        // Disposable CI MySQL values only (not production).
        FLASK_SECRET_KEY = 'ci-only-secret-not-for-production'
        MYSQL_DATABASE = 'c270_hotel_management_test'
        MYSQL_TEST_DATABASE = 'c270_hotel_management_test'
        MYSQL_USER = 'hotel_test'
        MYSQL_PASSWORD = 'hotel_test_password'
        MYSQL_ROOT_PASSWORD = 'ci-root-password'
        COMPOSE_PROJECT_NAME = 'c270hotelci'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_SHA = sh(returnStdout: true, script: 'git rev-parse --short=12 HEAD').trim()
                    env.GIT_SHA_FULL = sh(returnStdout: true, script: 'git rev-parse HEAD').trim()
                    env.IMAGE_TAG = "git-${env.GIT_SHA}"
                    env.LOCAL_IMAGE = "${env.ECR_REPOSITORY}:${env.IMAGE_TAG}"
                    echo "Immutable image tag: ${env.IMAGE_TAG}"
                }
            }
        }

        stage('Validate Workspace') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    command -v docker >/dev/null
                    docker compose version
                    test -f data.json
                    test -f Dockerfile
                    test -f docker-compose.yml
                    test -f scripts/migrate_json_to_mysql.py
                    test -f scripts/seed_dev_users.py
                    test -f scripts/aws/resolve_app_host.sh
                    test -f scripts/aws/deploy.sh
                    test -f scripts/aws/ensure_demo_users.sh
                    test -f scripts/aws/migrate_rooms.sh
                    test -f ansible/deploy_hotel_app.yml
                    if git ls-files --error-unmatch .env >/dev/null 2>&1; then
                      echo "ERROR: .env must not be tracked in Git" >&2
                      exit 1
                    fi
                    if git ls-files '*.pem' 2>/dev/null | grep -q .; then
                      echo "ERROR: PEM files must not be tracked in Git" >&2
                      exit 1
                    fi
                    python3 - <<'PY'
import json
rooms = json.load(open("data.json", encoding="utf-8")).get("rooms") or []
assert len(rooms) == 25, f"data.json must contain 25 rooms, found {len(rooms)}"
print("Validated data.json room source:", len(rooms))
PY
                    # Compose ${VAR:?} requires values for `config` only.
                    # Disposable CI placeholders — not used for AWS deploy (deploy uses Jenkins credentials).
                    export SEED_ADMIN_PASSWORD="${SEED_ADMIN_PASSWORD:-ci-validate-only}"
                    export SEED_USER_PASSWORD="${SEED_USER_PASSWORD:-ci-validate-only}"
                    export SEED_STEPH_PASSWORD="${SEED_STEPH_PASSWORD:-ci-validate-only}"
                    export COMPOSE_MYSQL_DATABASE="${COMPOSE_MYSQL_DATABASE:-${MYSQL_DATABASE}}"
                    export MYSQL_TEST_DATABASE="${MYSQL_TEST_DATABASE:-c270_hotel_management_test}"
                    docker compose -f docker-compose.yml config >/dev/null
                    echo "Workspace validation OK"
                '''
            }
        }

        stage('Install/Test Environment') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    mkdir -p reports artifacts
                    docker network create hotel-ci 2>/dev/null || true
                    docker rm -f hotel-ci-mysql 2>/dev/null || true
                    docker run -d --name hotel-ci-mysql --network hotel-ci \
                      -e MYSQL_DATABASE="$MYSQL_DATABASE" \
                      -e MYSQL_USER="$MYSQL_USER" \
                      -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
                      -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
                      mysql:8.4
                    for i in $(seq 1 60); do
                      if docker exec hotel-ci-mysql mysqladmin ping -h localhost -uroot -p"$MYSQL_ROOT_PASSWORD" --silent; then
                        echo "CI MySQL ready"
                        exit 0
                      fi
                      sleep 2
                    done
                    echo "ERROR: CI MySQL failed to become ready" >&2
                    exit 1
                '''
            }
        }

        stage('Python Syntax and Lint') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    docker run --rm --network hotel-ci \
                      -e PYTHONPATH=/app \
                      -v "$PWD:/app" -w /app python:3.11-slim \
                      sh -c 'pip install -q -r requirements.txt -r requirements-dev.txt && \
                             python -m compileall -q app.py config.py models.py repository.py scripts tests'
                '''
            }
        }

        stage('Focused Tests') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    # Intentionally do NOT set SEED_USER_PASSWORD (production path must never create generic "user").
                    docker run --rm --network hotel-ci \
                      -e PYTHONPATH=/app \
                      -e FLASK_SECRET_KEY="$FLASK_SECRET_KEY" \
                      -e MYSQL_HOST=hotel-ci-mysql -e MYSQL_PORT=3306 \
                      -e MYSQL_USER="$MYSQL_USER" -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
                      -e MYSQL_DATABASE="$MYSQL_DATABASE" \
                      -e MYSQL_TEST_DATABASE="$MYSQL_TEST_DATABASE" \
                      -v "$PWD:/app" -w /app python:3.11-slim \
                      sh -c 'pip install -q -r requirements.txt -r requirements-dev.txt && \
                             pytest -q tests/test_migrate_rooms.py tests/test_rooms_login_smoke.py tests/test_health_and_config.py \
                               --junitxml=reports/focused-junit.xml'
                '''
            }
        }

        stage('Full Test Suite') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    docker run --rm --network hotel-ci \
                      -e PYTHONPATH=/app \
                      -e FLASK_SECRET_KEY="$FLASK_SECRET_KEY" \
                      -e MYSQL_HOST=hotel-ci-mysql -e MYSQL_PORT=3306 \
                      -e MYSQL_USER="$MYSQL_USER" -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
                      -e MYSQL_DATABASE="$MYSQL_DATABASE" \
                      -e MYSQL_TEST_DATABASE="$MYSQL_TEST_DATABASE" \
                      -v "$PWD:/app" -w /app python:3.11-slim \
                      sh -c 'pip install -q -r requirements.txt -r requirements-dev.txt && \
                             pytest -q --junitxml=reports/pytest-junit.xml'
                '''
            }
            post {
                always {
                    sh 'docker rm -f hotel-ci-mysql 2>/dev/null || true'
                    junit allowEmptyResults: true, testResults: 'reports/*-junit.xml'
                }
            }
        }

        stage('Docker Build') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    docker build -t "${LOCAL_IMAGE}" .
                    echo "${LOCAL_IMAGE}" > artifacts/local_image.txt
                '''
            }
        }

        stage('Image Content Verification') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    docker run --rm --entrypoint '' "${LOCAL_IMAGE}" \
                      sh -c 'test -f /app/data.json && \
                             test -f /app/scripts/migrate_json_to_mysql.py && \
                             test -f /app/scripts/seed_dev_users.py && \
                             python - <<'"'"'PY'"'"'
import json
rooms = json.load(open("/app/data.json", encoding="utf-8")).get("rooms") or []
assert len(rooms) == 25, len(rooms)
print("image_data_json_rooms=", len(rooms))
PY'
                '''
            }
        }

        stage('Non-Root Verification') {
            when { expression { return !params.ROLLBACK_ONLY } }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    UID_VAL="$(docker run --rm --entrypoint '' "${LOCAL_IMAGE}" id -u)"
                    echo "image_uid=${UID_VAL}" | tee artifacts/nonroot.txt
                    test "${UID_VAL}" != "0"
                    test "${UID_VAL}" = "10001"
                '''
            }
        }

        stage('Trivy Security Scan') {
            when {
                allOf {
                    expression { return !params.ROLLBACK_ONLY }
                    expression { return params.RUN_SECURITY_SCAN }
                }
            }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    mkdir -p reports
                    # Gate: fail on HIGH/CRITICAL. Document unfixed base CVEs in reports/trivy-ignore.md when needed.
                    if command -v trivy >/dev/null 2>&1; then
                      trivy image --exit-code 1 --severity HIGH,CRITICAL \
                        --format table -o reports/trivy.txt \
                        "${LOCAL_IMAGE}" || { cat reports/trivy.txt; exit 1; }
                    else
                      docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
                        -v "$PWD/reports:/reports" aquasec/trivy:0.56.2 \
                        image --exit-code 1 --severity HIGH,CRITICAL \
                        --format table -o /reports/trivy.txt \
                        "${LOCAL_IMAGE}" || { cat reports/trivy.txt; exit 1; }
                    fi
                    echo "Trivy HIGH/CRITICAL gate passed" | tee -a reports/trivy.txt
                '''
            }
        }

        stage('ECR Authentication') {
            when {
                allOf {
                    expression { return !params.ROLLBACK_ONLY }
                    expression { return params.DEPLOY_TO_AWS }
                }
            }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
                    echo "${ACCOUNT_ID}" > artifacts/account_id.txt
                    REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
                    echo "${REGISTRY}" > artifacts/ecr_registry.txt
                    aws ecr get-login-password --region "${AWS_REGION}" \
                      | docker login --username AWS --password-stdin "${REGISTRY}"
                '''
            }
        }

        stage('ECR Push') {
            when {
                allOf {
                    expression { return !params.ROLLBACK_ONLY }
                    expression { return params.DEPLOY_TO_AWS }
                }
            }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    ACCOUNT_ID="$(cat artifacts/account_id.txt)"
                    REGISTRY="$(cat artifacts/ecr_registry.txt)"
                    ECR_IMAGE="${REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"
                    docker tag "${LOCAL_IMAGE}" "${ECR_IMAGE}"
                    docker push "${ECR_IMAGE}"
                    DIGEST="$(aws ecr describe-images \
                      --repository-name "${ECR_REPOSITORY}" \
                      --region "${AWS_REGION}" \
                      --image-ids imageTag="${IMAGE_TAG}" \
                      --query 'imageDetails[0].imageDigest' --output text)"
                    {
                      echo "ECR_IMAGE=${ECR_IMAGE}"
                      echo "ECR_DIGEST=${DIGEST}"
                      echo "IMAGE_TAG=${IMAGE_TAG}"
                    } | tee artifacts/ecr.env
                    echo "Pushed immutable image ${ECR_IMAGE} digest=${DIGEST}"
                '''
            }
        }

        stage('Resolve Application Host') {
            when {
                anyOf {
                    expression { return params.DEPLOY_TO_AWS }
                    expression { return params.ROLLBACK_ONLY }
                }
            }
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    chmod +x scripts/aws/resolve_app_host.sh
                    APP_HOST="$(AWS_REGION="${AWS_REGION}" C270_APP_INSTANCE_NAME="${APP_INSTANCE_NAME}" \
                      bash scripts/aws/resolve_app_host.sh)"
                    test -n "${APP_HOST}"
                    echo "${APP_HOST}" | tee artifacts/app_host.txt
                    mkdir -p ansible
                    cat > ansible/hosts.jenkins.ini <<EOF
[hotel_app]
${APP_HOST}

[hotel_app:vars]
ansible_user=ec2-user
ansible_ssh_private_key_file={{ lookup('env','SSH_KEY') }}
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args=-o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
EOF
                    echo "Resolved application host dynamically (not stored in Git)."
                '''
            }
        }

        stage('Deploy with Ansible') {
            when {
                allOf {
                    expression { return params.DEPLOY_TO_AWS }
                    expression { return !params.ROLLBACK_ONLY }
                }
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'hotel-ec2-ssh',
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    ),
                    string(credentialsId: 'hotel-seed-admin-password', variable: 'SEED_ADMIN_PASSWORD'),
                    string(credentialsId: 'hotel-seed-steph-password', variable: 'SEED_STEPH_PASSWORD')
                ]) {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        # shellcheck disable=SC1091
                        source artifacts/ecr.env
                        APP_HOST="$(cat artifacts/app_host.txt)"
                        # Record previous image for rollback (non-secret URI only).
                        set +x
                        PREV="$(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          "${SSH_USER}@${APP_HOST}" \
                          "cd '${APP_DIR}' && (grep -E '^APP_IMAGE=' .env | cut -d= -f2- || true)")"
                        set -x
                        echo "${PREV}" | tee artifacts/previous_image.txt

                        # Ensure demo seed passwords exist on host without printing values.
                        # Never set SEED_USER_PASSWORD on production.
                        set +x
                        scp -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          scripts/aws/update_prod_seed_env.sh \
                          "${SSH_USER}@${APP_HOST}:${APP_DIR}/scripts/aws/update_prod_seed_env.sh"
                        ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          "${SSH_USER}@${APP_HOST}" \
                          "chmod +x '${APP_DIR}/scripts/aws/update_prod_seed_env.sh' && \
                           cd '${APP_DIR}' && cp -a .env .env.bak.\$(date +%Y%m%d%H%M%S) && \
                           ENV_FILE='${APP_DIR}/.env' \
                           SEED_ADMIN_PASSWORD='${SEED_ADMIN_PASSWORD}' \
                           SEED_STEPH_PASSWORD='${SEED_STEPH_PASSWORD}' \
                           bash '${APP_DIR}/scripts/aws/update_prod_seed_env.sh'"
                        set -x

                        # Capture user count before deploy (must not increase unexpectedly).
                        set +x
                        BEFORE_USERS="$(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          "${SSH_USER}@${APP_HOST}" \
                          "cd '${APP_DIR}' && docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml exec -T db \
                            sh -lc 'mysql -N -u\"\$MYSQL_USER\" -p\"\$MYSQL_PASSWORD\" \"\$MYSQL_DATABASE\" -e \"SELECT COUNT(*) FROM users;\"'")"
                        set -x
                        echo "${BEFORE_USERS}" | tr -d '[:space:]' | tee artifacts/users_before.txt

                        INV=ansible/hosts.jenkins.ini
                        cat > "${INV}" <<EOF
[hotel_app]
${APP_HOST}

[hotel_app:vars]
ansible_user=${SSH_USER}
ansible_ssh_private_key_file=${SSH_KEY}
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args=-o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
EOF

                        if command -v ansible-playbook >/dev/null 2>&1; then
                          ansible-playbook -i "${INV}" ansible/deploy_hotel_app.yml \
                            -e "app_image=${ECR_IMAGE}" \
                            -e "run_deploy=true" \
                            -e "verify_rooms=true" \
                            -e "verify_demo_users=true"
                        else
                          docker run --rm \
                            -v "$PWD:/work" \
                            -v "${SSH_KEY}:/tmp/labsuser.pem:ro" \
                            -w /work --entrypoint /bin/sh \
                            cytopia/ansible:latest-tools \
                            -lc "mkdir -p /root/.ssh && cp /tmp/labsuser.pem /root/.ssh/labsuser.pem && chmod 600 /root/.ssh/labsuser.pem && \
                                 export PATH=/opt/venv/bin:\$PATH && \
                                 sed -i 's|ansible_ssh_private_key_file=.*|ansible_ssh_private_key_file=/root/.ssh/labsuser.pem|' ${INV} && \
                                 ansible-playbook -i ${INV} ansible/deploy_hotel_app.yml \
                                   -e app_image=${ECR_IMAGE} \
                                   -e run_deploy=true \
                                   -e verify_rooms=true \
                                   -e verify_demo_users=true"
                        fi
                    '''
                }
            }
        }

        stage('Post-Deployment Database Verification') {
            when {
                allOf {
                    expression { return params.DEPLOY_TO_AWS }
                    expression { return !params.ROLLBACK_ONLY }
                }
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'hotel-ec2-ssh',
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    )
                ]) {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        APP_HOST="$(cat artifacts/app_host.txt)"
                        BEFORE="$(tr -d '[:space:]' < artifacts/users_before.txt)"
                        ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          "${SSH_USER}@${APP_HOST}" \
                          "cd '${APP_DIR}' && docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml exec -T db \
                            sh -lc 'mysql -N -u\"\$MYSQL_USER\" -p\"\$MYSQL_PASSWORD\" \"\$MYSQL_DATABASE\" -e \"
                              SELECT COUNT(*) FROM rooms;
                              SELECT COUNT(*) FROM users WHERE username=\\\"admin\\\";
                              SELECT COUNT(*) FROM users WHERE username=\\\"steph\\\";
                              SELECT COUNT(*) FROM users;
                              SELECT COUNT(*) FROM bookings;
                              SELECT COUNT(*) FROM feedback;
                            \"'" \
                          | tee artifacts/db_verify.txt
                        ROOMS="$(sed -n '1p' artifacts/db_verify.txt | tr -d '[:space:]')"
                        ADMINS="$(sed -n '2p' artifacts/db_verify.txt | tr -d '[:space:]')"
                        STEPHS="$(sed -n '3p' artifacts/db_verify.txt | tr -d '[:space:]')"
                        USERS="$(sed -n '4p' artifacts/db_verify.txt | tr -d '[:space:]')"
                        # After Add Room, total may exceed 25; seed inventory must remain complete.
                        test "${ROOMS}" -ge 25
                        test "${ADMINS}" = "1"
                        test "${STEPHS}" = "1"
                        # Allow existing third user; forbid unexpected growth during this deploy.
                        test "${USERS}" -le "${BEFORE}"
                        echo "DB verification OK rooms=${ROOMS} admin=${ADMINS} steph=${STEPHS} users=${USERS} (before=${BEFORE})"
                    '''
                }
            }
        }

        stage('Health Verification') {
            when {
                anyOf {
                    expression { return params.DEPLOY_TO_AWS }
                    expression { return params.ROLLBACK_ONLY }
                }
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'hotel-ec2-ssh',
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    )
                ]) {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        APP_HOST="$(cat artifacts/app_host.txt)"
                        ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          "${SSH_USER}@${APP_HOST}" \
                          "set -euo pipefail
                           cd '${APP_DIR}'
                           curl -fsS http://127.0.0.1:5050/healthz | tee /tmp/hz.json
                           grep -q '\"status\"' /tmp/hz.json
                           grep -q 'ok' /tmp/hz.json
                           docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml ps
                           UID_VAL=\$(docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml exec -T app id -u)
                           test \"\$UID_VAL\" != 0
                           PS=\$(docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml ps)
                           echo \"\$PS\" | grep -vq '0.0.0.0:3306'
                          "
                        curl -fsS -o artifacts/public_healthz.json -w "%{http_code}" \
                          "http://${APP_HOST}:5050/healthz" | tee artifacts/public_health_code.txt
                        test "$(cat artifacts/public_health_code.txt)" = "200"
                        grep -q ok artifacts/public_healthz.json
                    '''
                }
            }
        }

        stage('Rollback') {
            when { expression { return params.ROLLBACK_ONLY } }
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'hotel-ec2-ssh',
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    )
                ]) {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        APP_HOST="$(cat artifacts/app_host.txt)"
                        # Prefer recorded previous_image; fall back to known-good rollback tag.
                        ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
                        ROLLBACK_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:manual-20260802-160243"
                        if [ -f artifacts/previous_image.txt ]; then
                          PREV="$(tr -d '[:space:]' < artifacts/previous_image.txt || true)"
                          if [ -n "${PREV}" ]; then ROLLBACK_URI="${PREV}"; fi
                        fi
                        echo "Rollback target (non-secret): ${ROLLBACK_URI}" | tee artifacts/rollback_target.txt
                        ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                          "${SSH_USER}@${APP_HOST}" \
                          "set -euo pipefail
                           cd '${APP_DIR}'
                           # Never: docker compose down --volumes
                           python3 - <<PY
from pathlib import Path
img = \"${ROLLBACK_URI}\"
path = Path('.env')
lines = path.read_text(encoding='utf-8').splitlines(True)
out, seen_app, seen_name = [], False, False
for line in lines:
    if line.startswith('APP_IMAGE='):
        out.append(f'APP_IMAGE={img}\\n'); seen_app = True
    elif line.startswith('IMAGE_NAME='):
        out.append(f'IMAGE_NAME={img}\\n'); seen_name = True
    else:
        out.append(line if line.endswith('\\n') else line + '\\n')
if not seen_app:
    out.append(f'APP_IMAGE={img}\\n')
if not seen_name:
    out.append(f'IMAGE_NAME={img}\\n')
path.write_text(''.join(out), encoding='utf-8')
path.chmod(0o600)
print('ROLLBACK_ENV_SET')
PY
                           aws ecr get-login-password --region '${AWS_REGION}' | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
                           docker pull '${ROLLBACK_URI}'
                           docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml up -d --no-deps app
                           for i in \$(seq 1 40); do
                             if curl -fsS http://127.0.0.1:5050/healthz | grep -q ok; then exit 0; fi
                             sleep 3
                           done
                           echo 'Rollback health check failed' >&2
                           exit 1
                          "
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**,artifacts/**', allowEmptyArchive: true
            sh '''#!/bin/bash
                docker rm -f hotel-ci-mysql 2>/dev/null || true
                rm -f ansible/hosts.jenkins.ini || true
            '''
        }
        failure {
            script {
                if (params.DEPLOY_TO_AWS && !params.ROLLBACK_ONLY) {
                    echo "Deploy failed — attempting automatic app-only rollback (MySQL volume preserved)."
                    try {
                        withCredentials([
                            sshUserPrivateKey(
                                credentialsId: 'hotel-ec2-ssh',
                                keyFileVariable: 'SSH_KEY',
                                usernameVariable: 'SSH_USER'
                            )
                        ]) {
                            sh '''#!/bin/bash
                                set -euo pipefail
                                if [ ! -f artifacts/app_host.txt ] || [ ! -f artifacts/previous_image.txt ]; then
                                  echo "Insufficient rollback context; manual rollback required."
                                  exit 0
                                fi
                                APP_HOST="$(cat artifacts/app_host.txt)"
                                PREV="$(tr -d '[:space:]' < artifacts/previous_image.txt)"
                                if [ -z "${PREV}" ]; then
                                  echo "No previous image recorded."
                                  exit 0
                                fi
                                ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
                                  "${SSH_USER}@${APP_HOST}" \
                                  "set -euo pipefail
                                   cd '${APP_DIR}'
                                   python3 - <<PY
from pathlib import Path
img = \"${PREV}\"
path = Path('.env')
lines = path.read_text(encoding='utf-8').splitlines(True)
out=[]
for line in lines:
    if line.startswith('APP_IMAGE=') or line.startswith('IMAGE_NAME='):
        key=line.split('=',1)[0]
        out.append(f'{key}={img}\\n')
    else:
        out.append(line if line.endswith('\\n') else line + '\\n')
path.write_text(''.join(out), encoding='utf-8')
path.chmod(0o600)
PY
                                   docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml pull app || true
                                   docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.mysql-fallback.yml up -d --no-deps app
                                   curl -fsS http://127.0.0.1:5050/healthz || true
                                  "
                            '''
                        }
                    } catch (err) {
                        echo "Automatic rollback encountered an error: ${err}"
                    }
                }
                echo "Pipeline failed. Do NOT delete the MySQL volume. Known rollback tag: manual-20260802-160243"
            }
        }
        success {
            echo "Pipeline succeeded. Immutable tag: ${env.IMAGE_TAG}"
        }
    }
}
