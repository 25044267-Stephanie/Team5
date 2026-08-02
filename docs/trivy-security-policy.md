# Trivy security policy (C270 Hotel Management)

This project treats container scanning as a **documented risk-management gate**, not as silent suppression.

## What Jenkins archives

| Artifact | Purpose | Exit behaviour |
|----------|---------|----------------|
| `reports/trivy-full.txt` | Complete HIGH/CRITICAL audit (fixed **and** unfixed) | Always archived; does not block by itself |
| `reports/trivy-gate.txt` | Fixable HIGH/CRITICAL only (`--ignore-unfixed`) | **Blocks** the pipeline on any finding |
| `reports/trivy-secrets.txt` | Secret detection in the image | **Blocks** on any detected secret |

`reports/trivy.txt` is a copy of the full audit for older evidence checklists.

## What blocks deployment

1. **Fixable** OS or language-package vulnerabilities at **HIGH** or **CRITICAL** severity.
2. **Any secret** detected in the built image.

Unfixed vendor/base-image findings (no Fixed Version from the distro yet) remain **visible** in `trivy-full.txt` for viva/evidence. They do not fail the gate until a fix is published and Trivy reports a Fixed Version — at which point the gate fails until we refresh the digest-pinned base image.

## Base image discipline

- Runtime/builder use an official `python:3.11-slim` image **pinned by immutable digest** in `Dockerfile`.
- Digests are refreshed periodically; candidates (including `python:3.11-slim-bookworm`) are compared with full vs fixable counts before changing the pin.
- Application Python dependencies are scanned; HIGH/CRITICAL app findings also fail the fixable gate.

## What this policy is not

- Not “ignore every CVE”.
- Not a blanket `.trivyignore` of individual CVE IDs.
- Not disabling Trivy or forcing `--exit-code 0` on the gate.

## Dry-run expectation

With `DEPLOY_TO_AWS=false` and `RUN_SECURITY_SCAN=true`:

- Full audit, fixable gate, and secret gate all run.
- ECR / Ansible deploy stages remain skipped.
- Pre-deploy failures must **not** attempt production rollback.
