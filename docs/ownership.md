# Component ownership map

Every FA DevOps / app component maps to exactly one owner.
Percentages and feature work come from the project presentation slides.

| Component / path | Owner | Assessed under |
|---|---|---|
| Main integration, login / role portals, special requests, testing & UI debug | Stephanie Ong (`25044267-Stephanie`) — Member 1 (50%) | Individual + Core |
| Room catalogue; room add/edit/delete; admin room pages; room images; booking-form & room validation support | AhmadAkmalRP — Member 2 (30%) | Individual |
| Booking list/management; check-in/out; booking↔room status; guest vs admin booking views; selected booking tests | 25043549-Daniel — Member 3 (15%) | Individual |
| `Dockerfile`, compose files, `.dockerignore`, `/healthz` | Stephanie Ong | Core — Containerisation |
| `requirements*.txt`, `pyproject.toml` | Stephanie Ong | CA2 + Core CI |
| `.github/workflows/ci.yml` | Stephanie Ong | Core — CI/CD |
| `.github/workflows/deploy-aws.yml`, `docker-compose.prod.yml`, `scripts/aws/*` | Stephanie Ong | Core — Deployment |
| Trivy HIGH/CRITICAL gate (in CI) | Stephanie Ong | Initiative — DevSecOps |
| CloudWatch agent + alarm scripts | Stephanie Ong | Initiative — Observability |
| `docs/*` ledgers & verification guides | Stephanie Ong | Individual understanding |
| `ansible/` (optional later) | TBD | Core — IaC |
| `Jenkinsfile` | Legacy — not demo path | CA2 narrative only |
