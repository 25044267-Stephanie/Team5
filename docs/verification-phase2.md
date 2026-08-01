# Phase 2 verification script (executable proof)

Stage A is covered below. Stage B (AWS) rows are placeholders until that stage is approved.

| What we're proving | Exact command / click-path | Expected output | If it fails |
|---|---|---|---|
| CI lint gate | Open green PR Actions run → job **Lint (ruff)** | Green; `All checks passed!` | Ruff rule break — fix code or adjust `pyproject.toml` |
| CI 111 tests + MySQL service | Same run → **Test (pytest + MySQL 8.4)** | Green; artifact `pytest-report-*` with JUnit | MySQL not healthy / env mismatch with `conftest.py` |
| CI image build (no push) | Same run → **Build image (Buildx)** | Green; short-SHA tag; no ECR/Docker Hub login | Dockerfile / Buildx cache issue |
| Trivy HIGH/CRITICAL gate | Same run → **Scan image (Trivy)** | Green when image clean; **red** blocks merge when HIGH/CRITICAL present | Unexpected CVE — upgrade/remove package or ask before `.trivyignore` |
| Test failure blocks build | PR [#4](https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/pull/4) / run with deliberate `assert False` | **Test** red; **Build** and **Scan** skipped | `set -o pipefail` missing on pytest\|tee |
| Trivy failure blocks merge | PR [#3](https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/pull/3) run with `setuptools==70.3.0` | Lint/Test/Build green; **Scan** red | Scan not using `exit-code: 1` |
| Green PR wall-clock | Run [30687309513](https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/actions/runs/30687309513) | ~3m17s total | Cold cache slower — pre-warm before demo |
| Local image + `/healthz` | `docker compose up --build -d` then `curl http://localhost:5050/healthz` | `{"status":"ok","database":"up"}` | Docker missing / DB env wrong |
| Non-root container | `docker compose exec app whoami` | `app` | `USER app` missing in Dockerfile |
| Local 111 tests | `py -3.11 -m pytest -q` with valid `.env` | `111 passed` | MySQL password mismatch for `hotel_app` |
| AWS RDS from app host only | Stage B — pending | connect OK from EC2; timeout elsewhere | SG / subnet misconfig |
| ECR pull via instance profile | Stage B — pending | `docker pull` succeeds without keys | IAM role / ECR policy |
| OIDC assume role | Stage B — pending | `aws sts get-caller-identity` in GHA | Trust policy repo/ref mismatch |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Pytest green but logs show failures | `pytest \| tee` without `pipefail` | Keep `set -o pipefail` in `ci.yml` |
| `ModuleNotFoundError: app` | Wrong cwd / not `python -m pytest` | Use `python -m pytest` from repo root |
| MySQL service not ready | Healthcheck too aggressive | Keep retries=30; never use fixed `sleep` |
| Trivy flags setuptools/wheel | Base image packaging tools | Strip unused packaging tools in Dockerfile (current approach) |
| Buildx slow | Cold GHA cache | Re-run once before demo |
| OIDC denied | Wrong `sub` / repo name in trust | Match `repo:OWNER/REPO:ref:refs/heads/main` |

## Demo-readiness (Stage A)

| Step | Live-safe? | Notes |
|---|---|---|
| Open green PR #1 Actions run | Yes | ~3–4 minutes wall; pre-run to warm cache |
| Show Trivy red run (#3) | Yes | Pre-recorded URL; do not re-merge vulnerable pin |
| Show test red run (#4) | Yes | After pipefail fix |
| Full cold CI from scratch | Risky in 15 min | Prefer pre-staged green + one short re-run |
| Stage B AWS live create | Not yet | Wait for Stage A approval |

**Stop:** Stage B must not start until you approve Stage A.
