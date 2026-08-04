# CA2 / Phase-1 enhancements & corrections

Ledger: **Enhancement / Correction from Phase 1 (CA2)** only.
Do not list Core pipeline/deploy work or Initiative items here.

| Date | What was wrong | Why it mattered | What changed | How verified |
|---|---|---|---|---|
| 2026-08-01 | `requirements.txt` unpinned; pytest mixed into runtime | Builds not reproducible; test tools in prod image | Pinned runtime deps; added `requirements-dev.txt` | `pip install -r requirements-dev.txt` in Python 3.11 venv |
| 2026-08-01 | Dockerfile single-stage, runs as root, no HEALTHCHECK, floating tag | Weak container story; no readiness signal | Multi-stage, digest-pinned base, `USER app`, HEALTHCHECK on `/healthz` | Pending: `docker compose up` + `docker exec … whoami` (needs Docker Desktop) |
| 2026-08-01 | No `/healthz` endpoint | Nothing for LB / smoke / Compose to probe | Added `/healthz` (JSON, 200/503, DB `SELECT 1`) | Pending Docker; unit suite still 111 tests (no test change) |
| 2026-08-01 | `.dockerignore` was listed in `.gitignore` | Ignore file would not be versioned | Fixed `.gitignore`; tidy `.dockerignore` | File present and no longer ignored |
| 2026-08-01 | `render.yaml` (0 bytes), empty `package-lock.json`, cache dirs in tree | Dead / noisy artifacts | Deleted stub + lockfile; removed `__pycache__` / `.pytest_cache` | Paths absent after cleanup |
| 2026-08-01 | `schema.sql` claimed "safe to re-run" but DROP TABLEs | Risk of wiping RDS/prod if used as migrate | Header warning; deploy path remains `init_db.py` only | Doc review of `database/schema.sql` |
| 2026-08-01 | `ZoneInfo("Asia/Singapore")` failed on Windows without system tz DB | App/tests could not import on some hosts | Pinned `tzdata==2025.2` in runtime requirements | Import + pytest after install |
| 2026-08-01 | No lint gate; unused imports in repo/scripts | Defects could land unnoticed | Added `ruff` + `pyproject.toml`; fixed unused imports / import order | `ruff check …` → All checks passed |
| 2026-08-01 | No GitHub Actions; only placeholder Jenkinsfile | No automated PR gate | Added `.github/workflows/ci.yml` (lint/test/build/Trivy) | Live green/red PR evidence in `docs/phase-2-verify.md` / `docs/verification-phase2.md` |
| 2026-08-01 | No production Compose / ECR-EC2 path | Could not demonstrate CD in Academy | Added `docker-compose.prod.yml`, `scripts/aws/*`, `deploy-aws.yml`, CloudWatch agent config | Local script syntax + ruff OK; live AWS pending Academy lab (`docs/aws-deployment.md`) |

## Kept pending your sign-off

- `data.json` / `data.json.bak` — legacy only; still on disk until you approve deletion.
- Empty `ansible/` stubs — optional later; not required for Academy EC2 Compose path.
