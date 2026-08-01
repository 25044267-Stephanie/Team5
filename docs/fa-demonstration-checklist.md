# C270 FA demonstration checklist

Organised for the Final Assessment rubric. Tick items during the live demo.

## 1. CI/CD pipeline evidence

- [ ] Open `.github/workflows/ci.yml` — explain lint → test → build → scan `needs` chain
- [ ] Open a **green** Actions run on `main` / PR
- [ ] Show pytest JUnit artifact
- [ ] Show Trivy report artifact
- [ ] Show a **red** test run that skipped Build/Scan
- [ ] Show a **red** Trivy run that blocked the pipeline
- [ ] Open `.github/workflows/deploy-aws.yml` — deploy only after CI success on `main`
- [ ] Show ECR image tagged with Git SHA (not `latest`-only)

## 2. Cloud deployment evidence

- [ ] EC2 Amazon Linux 2023 instance running in **us-east-1**
- [ ] Security group: 5050 (demo), 22 (trusted IP), **no 3306 public**
- [ ] `docker compose ps` — `app` and `db` healthy
- [ ] Public URL `http://<ec2>:5050` loads login
- [ ] `http://<ec2>:5050/healthz` returns `status=ok`
- [ ] IAM instance profile used for ECR pull (no keys on disk)

## 3. Containerisation & environment consistency

- [ ] Multi-stage Dockerfile, digest-pinned base
- [ ] `docker compose exec app whoami` → `app` (non-root)
- [ ] Gunicorn binds `0.0.0.0:5050`
- [ ] Same SHA image from CI/CD runs on EC2 (`APP_IMAGE`)
- [ ] Dev uses override build; prod uses `docker-compose.prod.yml` pull-only

## 4. Individual technical understanding

- [ ] Point to `docs/ownership.md` + README Team Contributions
- [ ] Each member explains their owned component in ≤60s

## 5. Technical initiative & depth

- [ ] Trivy HIGH/CRITICAL gate (Initiative ledger)
- [ ] CloudWatch logs + metrics + alarm demo
- [ ] Rollback via previous SHA tag

## 6. Improvements since CA2

- [ ] Pinned dependencies, `/healthz`, non-root image, GHA replacing placeholder Jenkins path
- [ ] `docs/CHANGELOG-FA.md` entries

---

## Recommended live demo flow (≈12–15 minutes)

1. GitHub Actions green run (pre-opened) — 1 min  
2. Explain gates + show red Trivy/test links — 2 min  
3. ECR SHA tag — 1 min  
4. EC2 `docker compose ps` + public app + `/healthz` — 2 min  
5. Create booking → MySQL select → restart app → data persists — 3 min  
6. CloudWatch logs + CPU metric + alarm — 2 min  
7. Rollback explanation + secrets/OIDC talking points — 2 min  

**Pre-stage:** warm CI, keep EC2 up, CloudWatch already receiving logs, alarm created.

---

## Assessor Q&A (concise model answers)

| Question | Model answer |
|---|---|
| What problem does Docker solve? | Packages app + runtime so laptop, CI, and EC2 run the same image. |
| Image vs container? | Image is the immutable template; container is a running instance. |
| Why multi-stage builds? | Build tools stay in builder; runtime image is smaller and cleaner. |
| Why non-root? | Limits blast radius if the process is compromised. |
| Why Gunicorn not Flask dev server? | Production WSGI server; Flask debug server is unsafe/unstable for prod. |
| Why port 5050? | App is configured for 5050; SG opens only what we demo. |
| Why not public 3306? | DB only on Compose network; reduces internet attack surface. |
| Why named volume? | MySQL data survives container recreate/restart. |
| What does `/healthz` check? | Process up **and** `SELECT 1` against MySQL; 200 vs 503. |
| CI vs CD? | CI validates every change; CD releases a tested artifact to an environment. |
| How does `needs` gate? | Later jobs do not start unless earlier jobs succeed. |
| Why Trivy? | Blocks known HIGH/CRITICAL vulns before deploy — DevSecOps control. |
| What is ECR? | Private registry for our SHA-tagged images. |
| What is EC2? | VM running Docker Engine + Compose for app and MySQL. |
| What is CloudWatch? | Logs, metrics, and alarms for operations visibility. |
| Logs vs metrics vs alarms? | Logs = events; metrics = numbers over time; alarms = thresholds on metrics. |
| Commit → image mapping? | Tag = Git SHA; deploy sets `APP_IMAGE` to that tag. |
| Failed deploy? | Workflow fails; previous containers/volume remain; fix forward or rollback. |
| Rollback? | `rollback.sh` redeploys previous SHA recorded under `state/`. |
| Why OIDC over long-lived keys? | Short-lived cloud creds from GitHub identity; no static keys in GitHub if Academy allows. |
| Academy limits? | Temporary account, us-east-1, IAM/OIDC may be restricted — documented fallback. |
