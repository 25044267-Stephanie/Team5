# Phase 2 verification script (executable proof)

Stage A (CI) and Stage B (AWS Academy / ECR / EC2 / CloudWatch) are both covered
below. Live AWS rows need your Academy lab session; local/CI rows can be proven
from this laptop or GitHub Actions.

| What we're proving | Exact command / click-path | Expected output | If it fails |
|---|---|---|---|
| CI lint gate | Open green PR Actions run → job **Lint (ruff)** | Green; `All checks passed!` | Ruff rule break — fix code or adjust `pyproject.toml` |
| CI 111 tests + MySQL service | Same run → **Test (pytest + MySQL 8.4)** | Green; artifact `pytest-report-*` with JUnit | MySQL not healthy / env mismatch with `conftest.py` |
| CI image build (no push) | Same run → **Build image (Buildx)** | Green; short-SHA tag; no ECR/Docker Hub login | Dockerfile / Buildx cache issue |
| Trivy HIGH/CRITICAL gate | Same run → **Scan image (Trivy)** | Green when image clean; **red** blocks merge when HIGH/CRITICAL present | Unexpected CVE — upgrade/remove package; do not weaken gate |
| Test failure blocks build | PR [#4](https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/pull/4) | **Test** red; **Build** and **Scan** skipped | `set -o pipefail` missing on pytest\|tee |
| Trivy failure blocks merge | PR [#3](https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/pull/3) | Lint/Test/Build green; **Scan** red | Scan not using `exit-code: 1` |
| Green PR wall-clock | Run [30687309513](https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/actions/runs/30687309513) | ~3m17s total | Cold cache slower — pre-warm before demo |
| Local image + `/healthz` | `docker compose up --build -d` then `curl http://localhost:5050/healthz` | `{"status":"ok","database":"up"}` | Docker missing / DB env wrong |
| Non-root container | `docker compose exec app whoami` | `app` | `USER app` missing in Dockerfile |
| Local 111 tests | `py -3.11 -m pytest -q` with valid `.env` | `111 passed` | MySQL password mismatch for `hotel_app` |
| ECR repo exists (idempotent) | `bash scripts/aws/create_ecr_repository.sh` | Prints URI; safe to rerun | Academy creds expired / wrong region |
| EC2 bootstrap (AL2023) | `sudo bash scripts/aws/bootstrap_ec2.sh` | Docker + compose + CW agent installed | Wrong AMI (not AL2023) |
| Prod Compose pulls image | `APP_IMAGE=…:SHA` in server `.env`; `bash scripts/aws/deploy.sh` | Containers healthy; `/healthz` ok | Bad `APP_IMAGE`, SG, or MYSQL_* secrets |
| MySQL not public | EC2 SG inbound list | No rule for 3306 | Remove accidental inbound 3306 |
| ECR pull via instance profile | On EC2: `aws ecr get-login-password … \| docker login …` then `docker pull` | Succeeds with **no** access keys in `~/.aws` | Attach ECR pull policy to instance role |
| CloudWatch logs | Console → Log groups `/c270/hotel/app`, `/c270/hotel/system` | Recent docker/agent events | Agent not started / IAM missing `logs:PutLogEvents` |
| CloudWatch metrics + alarm | Metrics `CWAgent` / `AWS/EC2`; alarm `c270-hotel-cpu-high` | Datapoints present; alarm OK or ALARM | Wrong InstanceId / region |
| CD after green CI on main | Actions → **Deploy AWS** after CI success | SHA image in ECR; public `/healthz` smoke green | Missing `production` env secrets; SSH/SG 22 |
| OIDC assume role (preferred) | Deploy job → Configure AWS via OIDC | `sts get-caller-identity` succeeds | Trust `sub` mismatch; Academy may block OIDC |
| Academy keys fallback | `AWS_AUTH_MODE=academy_keys` + temp secrets | Deploy can push to ECR | Keys expire when lab ends — refresh |
| Rollback previous SHA | `bash scripts/aws/rollback.sh` | Previous `APP_IMAGE` healthy again | No `state/previous_image` yet |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Pytest green but logs show failures | `pytest \| tee` without `pipefail` | Keep `set -o pipefail` in `ci.yml` |
| `ModuleNotFoundError: app` | Wrong cwd / not `python -m pytest` | Use `python -m pytest` from repo root |
| MySQL service not ready | Healthcheck too aggressive | Keep retries=30; never use fixed `sleep` |
| Trivy flags setuptools/wheel | Base image packaging tools | Strip unused packaging tools in Dockerfile (current approach) |
| Buildx slow | Cold GHA cache | Re-run once before demo |
| OIDC denied | Wrong `sub` / repo name in trust | Match `repo:OWNER/REPO:ref:refs/heads/main` |
| `IMMUTABLE` tag push fails | Re-pushing same tag | Always deploy a new commit SHA |
| Deploy health timeout | DB password / schema init | `docker compose logs app db`; check `.env` |
| Public smoke fails | SG missing 5050 or wrong `EC2_HOST` | Fix SG / secret; curl from laptop |

## Demo-readiness

| Step | Live-safe? | Notes |
|---|---|---|
| Open green CI Actions run | Yes | ~3–4 minutes wall; pre-run to warm cache |
| Show Trivy red run (#3) | Yes | Pre-recorded URL; do not re-merge vulnerable pin |
| Show test red run (#4) | Yes | After pipefail fix |
| Full cold CI from scratch | Risky in 15 min | Prefer pre-staged green + one short re-run |
| Stage B AWS live create | Needs Academy lab | Follow `docs/aws-deployment.md`; pre-warm EC2 + CW before viva |

Full Academy recreate steps: `docs/aws-deployment.md`.  
Assessor checklist: `docs/fa-demonstration-checklist.md`.
