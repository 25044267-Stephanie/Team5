# Technical initiative ledger

Work **beyond** the core brief. Each item needs a live ≤2-minute demo.
Do not double-count with Core or CA2.

| Item | Owner | Status | Demo script (≤2 min) |
|---|---|---|---|
| Trivy HIGH/CRITICAL gate in CI | Stephanie Ong | In `ci.yml` job `Scan image (Trivy)` | Open a failing Actions run where Trivy exits 1; or push a throwaway branch with a known-bad pin, show red scan, revert. |
| Auto-rollback on failed `/healthz` | TBD | Planned after deploy phase | Deploy bad tag → previous digest restores. |
| CloudWatch JSON logs + alarm | TBD | Stretch | Trigger alarm → ALARM state. |
