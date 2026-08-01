# AWS Academy deployment guide (us-east-1)

This guide recreates the full stack after an Academy lab wipe.

**Architecture:** GitHub Actions CI → ECR (SHA tag) → EC2 Amazon Linux 2023
(Docker Compose: Flask app + MySQL volume) → CloudWatch logs/metrics/alarm.

MySQL runs **in Docker on EC2** (not RDS) so the demo stays within typical
Academy limits and stays easy to tear down.

## Screenshot checkpoints

Mark these as you go: ☐ lab started · ☐ ECR URI · ☐ EC2 running · ☐ SG rules ·
☐ `/healthz` OK · ☐ CloudWatch logs · ☐ Alarm · ☐ Actions deploy green

---

## 1. Start the AWS Academy lab

1. Open AWS Academy → Learner Lab → **Start Lab**.
2. Wait until the status is green / AWS ready.
3. Open **AWS Details** and note temporary credentials if you need the Academy fallback.

## 2. Confirm region `us-east-1`

Console top-right region selector → **US East (N. Virginia)**.

CLI check:

```bash
aws configure get region
# or
echo $AWS_REGION
```

Expected: `us-east-1`.

## 3. Create / confirm ECR repository

From a machine with Academy AWS CLI credentials:

```bash
export AWS_REGION=us-east-1
export ECR_REPOSITORY=c270-hotel-management
bash scripts/aws/create_ecr_repository.sh
```

Expected: prints `ECR repository URI: <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/c270-hotel-management`.

☐ Screenshot: ECR repository page showing scan-on-push.

## 4–7. Launch Amazon Linux 2023 EC2

1. EC2 → Launch instance.
2. Name: `c270-hotel-ec2`.
3. AMI: **Amazon Linux 2023**.
4. Instance type: `t2.micro` or `t3.micro` (lab-permitted).
5. Key pair: create/download PEM (store outside git).
6. Network: default VPC OK for Academy.
7. Security group inbound:
   - **22/tcp** from *your* IP / classroom CIDR only
   - **5050/tcp** from `0.0.0.0/0` (demo) or classroom CIDR
   - **No 3306 inbound**
8. Advanced → IAM instance profile: role with ECR pull + CloudWatch
   (see `docs/aws/iam-policies.md`). If Academy blocks custom roles, use the
   voclabs / lab role if it already allows ECR + logs, or attach the nearest
   permitted policy and note the limitation for assessors.

☐ Screenshot: instance **Running** + security group rules.

## 8. Bootstrap EC2

SSH:

```bash
ssh -i /path/to/key.pem ec2-user@EC2_PUBLIC_DNS
```

Upload or `git clone` the repo, then:

```bash
cd Team5_HotelManagement_Project   # or your copy path
sudo bash scripts/aws/bootstrap_ec2.sh
# log out and back in so docker group applies
exit
ssh -i /path/to/key.pem ec2-user@EC2_PUBLIC_DNS
docker compose version
```

Copy deploy files into `/opt/c270-hotel-management`:

```bash
sudo mkdir -p /opt/c270-hotel-management
sudo chown ec2-user:ec2-user /opt/c270-hotel-management
rsync -a docker-compose.prod.yml database scripts cloudwatch \
  /opt/c270-hotel-management/
chmod +x /opt/c270-hotel-management/scripts/aws/*.sh
```

## 9. Create server-side `.env` (never commit)

```bash
nano /opt/c270-hotel-management/.env
```

Minimum keys (placeholders shown):

```env
FLASK_SECRET_KEY=use-a-long-random-string
MYSQL_HOST=db
MYSQL_PORT=3306
MYSQL_USER=hotel_app
MYSQL_PASSWORD=choose-strong-password
MYSQL_DATABASE=hotel_management
MYSQL_ROOT_PASSWORD=choose-different-strong-password
SEED_ADMIN_PASSWORD=change-me
SEED_USER_PASSWORD=change-me
APP_IMAGE=ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/c270-hotel-management:GIT_SHA
```

`MYSQL_HOST=db` is the Compose service name.

## 10–11. First deploy (manual)

```bash
export AWS_REGION=us-east-1
# set APP_IMAGE in .env to a pushed SHA tag first, then:
bash /opt/c270-hotel-management/scripts/aws/deploy.sh
curl -fsS http://127.0.0.1:5050/healthz
```

Expected JSON includes `"status":"ok","database":"up"`.

From your laptop: `http://EC2_PUBLIC_DNS:5050/` and `/healthz`.

☐ Screenshot: browser login page + `/healthz` JSON.

## 12–15. CloudWatch

```bash
sudo bash /opt/c270-hotel-management/scripts/aws/configure_cloudwatch.sh
```

Console:

1. **Log groups** `/c270/hotel/app` and `/c270/hotel/system`
2. **Metrics** → `CWAgent` (mem/disk/cpu)
3. Alarm:

```bash
export INSTANCE_ID=i-xxxxxxxx
bash scripts/aws/create_cpu_alarm.sh
```

☐ Screenshot: log events + alarm **OK** or **ALARM** after a stress test.

### Logging approach (why)

Containers use Docker **json-file** logging with rotation (`max-size` /
`max-file`) in `docker-compose.prod.yml`. The CloudWatch agent tails
`/var/lib/docker/containers/*/*-json.log` into `/c270/hotel/app`.

This avoids baking secrets into an `awslogs` driver config and works on
Amazon Linux 2023 with the unified agent.

## 16. GitHub configuration

Repo → **Settings → Environments → production** (required reviewers optional but recommended).

### Variables

| Name | Example |
|---|---|
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `c270-hotel-management` |
| `AWS_AUTH_MODE` | `oidc` or `academy_keys` |

### Secrets (Environment `production`)

| Name | When |
|---|---|
| `AWS_ROLE_TO_ASSUME` | OIDC mode |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` | Academy fallback only |
| `EC2_HOST` | Public DNS/IP |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_PRIVATE_KEY` | PEM private key |

Branch protection on `main`: require CI jobs
`Lint (ruff)`, `Test (pytest + MySQL 8.4)`, `Build image (Buildx)`,
`Scan image (Trivy)`.

## 17–18. CI then CD

1. Merge a green PR to `main` (CI must pass including Trivy).
2. Workflow **Deploy AWS** runs after successful CI on `main`
   (or use **workflow_dispatch**).
3. It builds the **same commit**, pushes `:SHORT_SHA` to ECR, SSHes to EC2,
   runs `deploy.sh`, then curls public `/healthz`.

**Why SHA-only tags (no floating `main` / `latest`):** the ECR repository is
created with **IMMUTABLE** image tags. Re-pushing `main` would fail on the
second deploy. The Git SHA is the single source of truth for which commit is
live.

## 19. Verification checklist

- [ ] GitHub Actions CI green on the commit
- [ ] Deploy AWS green
- [ ] ECR shows immutable SHA tag
- [ ] `docker compose -f docker-compose.prod.yml ps` healthy on EC2
- [ ] App UI on `:5050`
- [ ] `/healthz` → ok
- [ ] Create a booking → row in MySQL (`docker compose exec db mysql ...`)
- [ ] Restart app container → data still present (named volume)
- [ ] CloudWatch logs receiving lines
- [ ] Alarm visible

## 20. Rollback

```bash
bash /opt/c270-hotel-management/scripts/aws/rollback.sh
# or
bash /opt/c270-hotel-management/scripts/aws/rollback.sh ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/c270-hotel-management:OLDSHA
```

## 21. Troubleshooting

| Problem | Fix |
|---|---|
| `docker login` ECR fails | Instance role missing `ecr:GetAuthorizationToken` / pull actions |
| App unhealthy | `docker compose logs app` — usually bad MYSQL_PASSWORD or DB not ready |
| Public curl fails | SG missing 5050, or host firewall |
| Deploy workflow cannot SSH | Wrong `EC2_HOST` / key / SG 22 source IP |
| OIDC assume role denied | Trust `sub` must match `repo:OWNER/REPO:ref:refs/heads/main` |
| Academy keys expired | Refresh from Learner Lab AWS Details |
| Trivy blocks CI | Fix vulns (do not ignore to force green) |
| IMMUTABLE tag re-push | Use a new commit SHA; never retag |

## 22–23. Cleanup / next lab session

Before leaving:

```bash
docker compose -f /opt/c270-hotel-management/docker-compose.prod.yml --env-file /opt/c270-hotel-management/.env down
# Do NOT add --volumes unless you intend to wipe MySQL data
```

Console: terminate EC2, delete ECR images/repo if required by instructor, delete alarm, delete log groups if needed.

Next session: Start Lab → recreate ECR (`create_ecr_repository.sh`) → new EC2 → bootstrap → restore `.env` → push/deploy again.
