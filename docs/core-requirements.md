# Core requirements ledger

Work that fulfils the FA brief (pipeline, deployment, containerisation).
Do **not** list Initiative-only or CA2-only items here.

| Component | Status | Evidence | Owner |
|---|---|---|---|
| Containerisation (multi-stage, non-root, digest, HEALTHCHECK, compose split) | Implemented | `Dockerfile`, compose files | Stephanie Ong |
| `/healthz` readiness probe | Implemented | `app.py` | Stephanie Ong |
| CI pipeline lint → test → build (gates) | In progress (Stage A) | `.github/workflows/ci.yml` | Stephanie Ong |
| Cloud deployment (EC2 + RDS + public URL) | Not started | Stage B / later | Stephanie Ong |
| Ansible host config | Stub | later phase | TBD |
| CD + rollback on `main` | Not started | later phase | TBD |
