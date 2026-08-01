# Technical initiative ledger

Work **beyond** the core brief. Each item needs a live ≤2-minute demo artifact.
Do not double-count with Core or CA2.

| Item | Owner | Status | Demo script (≤2 min) |
|---|---|---|---|
| Trivy HIGH/CRITICAL gate in CI | TBD | Integrated in `.github/workflows/ci.yml` `build-and-scan` | 1. Open Actions run → expand **Trivy scan**. 2. On a throwaway branch, temporarily add a known-bad package or remove `ignore-unfixed` / lower base image; push; show the job fail red and block merge. 3. Revert. |
| Auto-rollback on failed `/healthz` | TBD | Planned Phase 5/6 | Deploy bad tag → watch previous digest restore. |
| CloudWatch JSON logs + alarm | TBD | Stretch only | Trigger alarm → show ALARM state. |
