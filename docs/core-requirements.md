# Core requirements ledger

Work that fulfils the FA brief (pipeline, deployment, containerisation).
Do **not** list Initiative-only or CA2-only items here.

| Component | Status | Evidence | Owner |
|---|---|---|---|
| Containerisation (multi-stage, non-root, digest, HEALTHCHECK, compose) | Implemented | `Dockerfile`, compose files | Stephanie Ong |
| `/healthz` readiness probe | Implemented | `app.py` | Stephanie Ong |
| CI pipeline lint → test → build → scan | Implemented | `.github/workflows/ci.yml` | Stephanie Ong |
| Cloud deployment (EC2 + Compose MySQL + ECR SHA deploy) | Documented + scripts (needs Academy run) | `docker-compose.prod.yml`, `deploy-aws.yml`, `docs/aws-deployment.md` | Stephanie Ong |
| Ansible host config | Stub only | `ansible/` | TBD |
