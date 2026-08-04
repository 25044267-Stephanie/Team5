# Technical initiative ledger

Work **beyond** the core brief. Each item needs a live ≤2-minute demo.
Do not double-count with Core or CA2.

| Item | Owner | Status | Demo script (≤2 min) |
|---|---|---|---|
| Trivy HIGH/CRITICAL gate in CI | Stephanie Ong | Live in `ci.yml` | Open a red Scan job (deliberate vulnerable pin) or green scan artifact |
| CloudWatch logs + metrics + CPU alarm | Stephanie Ong | Config + scripts ready | Show `/c270/hotel/app` log events + `c270-hotel-cpu-high` alarm |
| Auto-rollback script | Stephanie Ong | `scripts/aws/rollback.sh` | Redeploy previous SHA from `state/previous_image` |
