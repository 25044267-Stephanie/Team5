# C270 checklist status (updated after config/Jenkins repair)

## Done

- [x] Jenkins EC2 + job + 3 credentials
- [x] App EC2 healthy (non-root, MySQL private)
- [x] Jenkinsfile parse / compose validate fixes (`e321e21`, `b6d25ee`)
- [x] Docker Compose plugin on Jenkins
- [x] Config/_engine_options + URI encoding aligned with tests (`31506e1`)
- [x] Jenkins rollback guard (only after deployment starts) (`31506e1`)
- [x] skipDefaultCheckout to avoid duplicate SCM checkout (`31506e1`)
- [x] Clean-container focused + full tests green (140 passed)

## Current (connectivity)

- [ ] AWS Academy Learner Lab started + CLI credential block on clipboard
- [ ] Run `scripts/aws/Recover-C270Environment.ps1` with Start/Repair/Check/OpenBrowser
- [ ] External Jenkins login page HTTP 200/302/403 (not a bookmarked old IP)

## Next (you click)

- [ ] Jenkins dry-run on tip `aedb66d` (`ci/github-actions`)
  - Job: `c270-hotel-management-pipeline`
  - Build with Parameters:
    - `DEPLOY_TO_AWS=false`
    - `RUN_SECURITY_SCAN=true`
    - `ROLLBACK_ONLY=false`
  - Confirm Trivy archives `trivy-full.txt`, `trivy-gate.txt`, `trivy-secrets.txt`
  - Gate must pass (fixable HIGH/CRITICAL = 0); full audit may still list unfixed OS CVEs
  - Deploy stages skipped; no rollback attempt

## After dry-run green

- [ ] Full deploy `DEPLOY_TO_AWS=true`
- [ ] Browser gate (admin / steph / rooms / booking / feedback / logout)
- [ ] Rollback evidence `ROLLBACK_ONLY=true`
- [ ] Webhook (update URL after every lab restart)
- [ ] GitHub Actions green CI (no AWS deploy)
