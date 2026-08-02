# FA L4 evidence checklist — C270 Hotel Management

Collect screenshots / command output for each item. **Never capture passwords, PEM keys, or `.env` contents.**

## Verified room source

| Item | Value |
|------|--------|
| Source of truth | `data.json` (25 rooms) |
| Do **not** use | `data.json.bak` (3 stub rooms 101–103) |
| Root cause of EC2 `room_count=0` | ECR/app image excluded `data.json`; prod Compose never ran migrate; MySQL volume already existed so `/docker-entrypoint-initdb.d` did not re-run |
| After Add Room | total rooms **>= 25**; all **25 seed** numbers must remain; seed rooms cannot be deleted |

## GitHub Actions (CI only)

- [ ] Workflow `C270 CI Quality Gate` (`.github/workflows/ci.yml`)
- [ ] Secrets `CI_SEED_ADMIN_PASSWORD` / `CI_SEED_STEPH_PASSWORD` configured
- [ ] Green run: focused tests, full tests, Docker build, non-root, Trivy
- [ ] Artifacts downloadable
- [ ] `Deploy AWS` workflow is **workflow_dispatch only** (Jenkins deploys)

## Containerisation

- [ ] `Dockerfile` present (non-root `USER app`)
- [ ] Local image build succeeds
- [ ] Image contains `/app/data.json` and migrate script
- [ ] Local `app` + `db` healthy
- [ ] Local `curl http://127.0.0.1:5050/healthz` → HTTP 200, database up
- [ ] Local `SELECT COUNT(*) FROM rooms` → **25**
- [ ] Second migrate run → 0 inserted / all skipped

## AWS deployment

- [ ] ECR repository `c270-hotel-management`
- [ ] New immutable tag (not overwriting `manual-20260802-160243`)
- [ ] ECR image digest recorded
- [ ] EC2 status checks passed; IAM role attached
- [ ] Security group: 22 + 5050 only (no public 3306)
- [ ] Docker + Compose versions on EC2
- [ ] EC2 app + db healthy
- [ ] Internal + public `/healthz` HTTP 200
- [ ] Original 25 rooms visible in UI
- [ ] User booking saved; admin can view booking
- [ ] Feedback still works

## Ansible

- [ ] `ansible-playbook ... --syntax-check`
- [ ] `--check` mode (where practical)
- [ ] First real run succeeds
- [ ] Second real run mostly unchanged / idempotent
- [ ] Deploy with `-e run_deploy=true` leaves `room_count > 0`

## Jenkins

- [ ] Separate `c270-jenkins` EC2 (not on app host)
- [ ] `Start-C270Jenkins.ps1` discovers current Jenkins IP
- [ ] Bootstrap: Java 21, Jenkins, Git, Docker, AWS CLI, Ansible, Trivy
- [ ] Credentials: `hotel-ec2-ssh`, `hotel-seed-admin-password`, `hotel-seed-steph-password`
- [ ] Dry-run: `DEPLOY_TO_AWS=false` green (Checkout → Validate → Tests → Build → Non-root → Trivy)
- [ ] Full run: ECR immutable `git-<sha>` push + dynamic host resolve + Ansible deploy
- [ ] Post-deploy: room_count=25; one admin; one steph; health 200; no public 3306
- [ ] Rollback evidence (`ROLLBACK_ONLY` or failure path); tag `manual-20260802-160243`
- [ ] Webhook only after manual full pipeline is green

## GitHub webhook

- [ ] Webhook URL → Jenkins
- [ ] Content-Type `application/json`
- [ ] Secret configured (not committed)
- [ ] Push events; delivery **2xx**
- [ ] Automatic Jenkins trigger after push

## Safety reminders

- Never `docker compose down --volumes` on the production MySQL volume
- Never publish MySQL 3306 publicly
- AWS Academy stop/start may change the public IPv4 — update DNS/docs/webhook SG as needed
