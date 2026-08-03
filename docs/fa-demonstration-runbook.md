# C270 Hotel Management — FA demonstration runbook (L4)

Do not store passwords, PEM contents, or AWS temporary keys in this file.

## Before you start

1. Start the **AWS Academy Learner Lab** (credentials expire often).
2. Confirm region **us-east-1**.
3. Copy the newest AWS Academy **CLI** credential block to the Windows clipboard
   (do not paste keys into chat).
4. Recover Jenkins + app connectivity in one command from the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ".\scripts\aws\Recover-C270Environment.ps1" `
  -StartInstances -RepairSecurityGroups -RepairJenkins `
  -CheckApplication -CheckJenkins -OpenBrowser
```

This rediscovers current public IPs, repairs managed `/32` SG rules for your
current client IP, verifies Jenkins/Docker, and opens the Jenkins login page.
Never reuse a bookmarked Jenkins URL after a lab restart.

Optional app-only helper (writes gitignored `ansible/hosts.ini`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\aws\Start-C270Lab.ps1 -StartInstance -OpenBrowser
```

## Demonstration order

1. Run `Start-C270Lab.ps1` and show the discovered IP.
2. Open the public website URL it prints.
3. Log in as `steph` and show all **25** rooms / booking.
4. Log in as `admin` and show the booking / admin views.
5. Show ECR image tag `room-fix-20260802-184257` (do not overwrite rollback tag).
6. On EC2: `docker compose … ps` — app healthy, db `3306/tcp` only.
7. Show `SELECT COUNT(*) FROM rooms` → **25**.
8. Ansible first run + second idempotent run (PLAY RECAP).
9. Jenkins: run `Recover-C270Environment.ps1` (or `Start-C270Jenkins.ps1 -OpenBrowser`); IP changes after Academy restart.
10. Show dry-run (`DEPLOY_TO_AWS=false`) on `ci/github-actions` tip `aedb66d`, then full deploy (`DEPLOY_TO_AWS=true`).
11. Show Trivy full/gate/secrets, ECR `git-<sha>` tag + digest, dynamic app host resolve, Ansible.
12. Confirm room_count 25, admin/steph once each, `/healthz` 200.
13. GitHub webhook 2xx delivery (only after manual full pipeline is green).
14. Explain rollback to `manual-20260802-160243` (app only; keep MySQL volume).
15. Stop `c270-hotel-app` and `c270-jenkins` after the demo (closing the browser does **not** stop AWS).

### Why these choices (short talking points)

- **Separate Jenkins EC2** — CI must not share the app container/host blast radius.
- **Immutable tags** — never overwrite `latest`; audit with Git SHA.
- **Tests gate deploy** — broken code never reaches EC2.
- **Trivy gate** — HIGH/CRITICAL findings block promotion.
- **Ansible** — repeatable deploy + verify (rooms, accounts, health, non-root, private MySQL).
- **Dynamic IP** — AWS Academy public IPv4 changes; never hardcode.
- **Rooms-only + admin/steph ensure** — preserve data; do not full-seed generic users.

## Rollback (application image only)

On EC2 under `/home/ec2-user/c270-hotel-management`, set `APP_IMAGE` /
`IMAGE_NAME` to:

`…/c270-hotel-management:manual-20260802-160243`

Then pull and `up -d --no-deps app`. Never `docker compose down --volumes`.

## Safety reminders

- Never expose MySQL **3306** publicly.
- Never commit `ansible/hosts.ini`, `.env`, or `*.pem`.
- Public IPv4 changes after Academy stop/start — re-run `Start-C270Lab.ps1`.
