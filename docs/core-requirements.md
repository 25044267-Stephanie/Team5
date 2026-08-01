# Core requirements ledger

Work that fulfils the FA brief (pipeline, deployment, containerisation).
Do not list Initiative or CA2-only items here.

| Component | Status | Evidence | Owner |
|---|---|---|---|
| Containerisation (multi-stage, non-root, digest, HEALTHCHECK, compose split) | Implemented locally; Docker Desktop verify pending | `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `docs/phase-1-verify.md` | TBD |
| `/healthz` readiness probe | Implemented | `app.py` `healthz()` | TBD |
| CI pipeline (lint → test → build → Trivy gate) | Implemented in repo; live green PR pending | `.github/workflows/ci.yml`, `docs/phase-2-verify.md` | TBD |
| Cloud deployment (EC2 + RDS + public URL) | Not started | Phase 3–5 | TBD |
| Ansible host config | Stub only | Phase 4 | TBD |
| CD + rollback on `main` | Not started | Phase 5 | TBD |
