# Phase 2 verification — GitHub Actions CI

## What the pipeline does

```
PR / push
  ├─ Lint (ruff)          ─┐
  ├─ Test (pytest+MySQL)  ─┴─ must both pass
  └─ Buildx image → Trivy (fails on fixable HIGH/CRITICAL)
```

Artifacts uploaded every run: `pytest-report-*`, `trivy-report-*`.

## 0. Prerequisites (you must do these once)

1. Install [Git](https://git-scm.com/) (already present on this machine) and [GitHub CLI](https://cli.github.com/) optional.
2. Create an empty GitHub repository (do **not** add a README on GitHub if you will push this tree).
3. From the project root:

```powershell
cd "c:\Users\steph\Downloads\FA FINAL\FA FINAL\C270_Hotel_Management_Feeback_Ver"

git init -b main
git add .
git status
# CONFIRM .env is NOT listed. If it is, stop and fix .gitignore.
```

4. Commit and push (replace `YOUR_USER/YOUR_REPO`):

```powershell
git commit -m "ci: add GitHub Actions lint, test, build, and Trivy gate"
git remote add origin https://github.com/25044267-Stephanie/Team5_HotelManagement_Project.git
git push -u origin main
```

Team remote (already wired locally):  
https://github.com/25044267-Stephanie/Team5_HotelManagement_Project  

CI branch pushed: `devops/ci-pipeline`  
Open PR: https://github.com/25044267-Stephanie/Team5_HotelManagement_Project/pull/new/devops/ci-pipeline

5. GitHub → **Settings → Branches → Add branch protection rule** for `main`:
   - Require a pull request before merging
   - Require status checks: `Lint (ruff)`, `Test (pytest + MySQL 8.4)`, `Build image + Trivy scan`
   - Do not allow bypassing if you can avoid it

## 1. Green run (excellence evidence)

```powershell
git checkout -b chore/ci-green-proof
git push -u origin chore/ci-green-proof
gh pr create --title "ci: prove green pipeline" --body "Phase 2 gate"
```

Or open a PR in the GitHub UI.

**Expected:** all three jobs green. Copy the Actions run URL and note per-job timing
(job summary page). Download the pytest artifact and confirm 111 tests.

## 2. Red run that blocks merge (excellence evidence)

On a throwaway branch:

```powershell
git checkout -b chore/ci-red-proof
```

Edit any test temporarily, e.g. in `tests/test_app.py` add at the top of a test body:

```python
assert False, "deliberate CI failure for Phase 2 demo"
```

```powershell
git commit -am "test: deliberate failure for CI gate demo"
git push -u origin chore/ci-red-proof
# open PR
```

**Expected:** `Test (pytest + MySQL 8.4)` red; `Build image + Trivy scan` skipped
(because it `needs: [lint, test]`). Merge button blocked by required checks.

Revert the deliberate failure before merging anything else.

## 3. Local lint (optional, no Docker required)

```powershell
py -3.11 -m pip install -r requirements-dev.txt
ruff check app.py config.py models.py repository.py scripts tests
```

Expected: `All checks passed!`

## Demo risk notes

| Risk | Fallback |
|---|---|
| Full CI > 10 minutes cold | Keep a pre-recorded green run; GHA cache warms Buildx |
| Trivy fails on a new CVE the day of demo | Show the failing job as the DevSecOps control working; fix by bumping base digest on a hotfix branch |
| MySQL service slow to healthy | Retries=30 in workflow; re-run job |
