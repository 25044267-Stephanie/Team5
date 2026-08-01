# Component ownership map

Every file created for FA DevOps work must map to exactly one owner.
Fill names before the demo. Until then owners are `TBD`.

| Component / path | Owner | Assessed under |
|---|---|---|
| `Dockerfile`, compose files, `.dockerignore` | TBD | Core — Containerisation |
| `app.py` `/healthz` | TBD | Core — Deployment readiness |
| `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` | TBD | CA2 + Core CI |
| `.github/workflows/ci.yml` | TBD | Core — CI/CD (+ Trivy in Initiative) |
| `docs/phase-1-verify.md`, `docs/phase-2-verify.md` | TBD | Individual understanding |
| `docs/CHANGELOG-FA.md` | TBD | CA2 |
| `docs/core-requirements.md` / `initiative.md` | TBD | Ledgers |
| `ansible/` | TBD | Core — IaC (Phase 4) |
| `Jenkinsfile` | Legacy — not demo path | CA2 narrative only |
