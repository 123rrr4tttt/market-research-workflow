<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/10_B-line-round3-r3-must-minimal-implementation.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/10_B-line-round3-r3-must-minimal-implementation.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# B-Line Round3 R3 Must Minimal Implementation (2026-03-04)

## 0. Scope
- Task window: Wed 2026-03-04 00:15 PST
- Goal: implement and verify R3 minimal Must set from scout reference pack
- Priority: quality engineering (test pyramid + CI fail-stop), with rollback, observability, and security as first-class gates

## 1. Repo-level Mapping (R3-1)

### 1.1 Key directories
- Core runtime: `main/backend/`
- Ops/deploy and rollback path: `main/ops/`, `scripts/docker-deploy.sh`
- CI gate entry: `.github/workflows/backend-tests.yml`
- Test pyramid: `main/backend/tests/{unit,integration,contract,e2e}` + `main/backend/pytest.ini`
- Development docs first entry: `development/latest-dev-docs/`

### 1.2 Existing test/CI/observability/release-rollback files
- Tests: `main/backend/tests/README.md`, `main/backend/pytest.ini`, `scripts/test-standardize.sh`
- CI: `.github/workflows/backend-tests.yml`
- Observability: `main/backend/app/main.py` (`/metrics`, `/api/v1/health`, `/api/v1/health/deep`), `main/backend/app/services/job_logger.py`
- Release/rollback: `main/ops/start-all.sh`, `main/ops/stop-all.sh`, `main/ops/restart.sh`, `scripts/docker-deploy.sh`, `main/backend/docker-entrypoint.sh`

## 2. Minimal Implementation (R3-2)

### 2.1 Quality engineering Must
- Keep test pyramid enforcement by marker/job split (`unit`, `integration`, `contract`, `e2e`).
- Change CI policy to fail-stop on PR and mainline for schema + coverage gates.

### 2.2 Rollback Must
- Add `rollback-drill` command to `scripts/docker-deploy.sh`:
  - supports `--profile <name>`, `--dry-run`, `--skip-preflight`
  - default flow: preflight -> stop -> start -> health -> deep health -> stop
- Add operation entry in `main/ops/README.md`.

### 2.3 Security Must
- Add blocking `security-check` job to CI:
  - SAST: `bandit -r main/backend/app`
  - dependency vulnerability scan: `pip-audit -r main/backend/requirements.txt --strict`
  - secret scanning: `gitleaks/gitleaks-action@v2`

### 2.4 Observability emphasis
- Reuse existing observability endpoints as rollback-drill acceptance gate:
  - `GET /api/v1/health`
  - `GET /api/v1/health/deep`

## 3. Reference Mapping (R3-3)

### 3.1 `reference_pack.md` -> concrete changes
- B line Must: "test pyramid" + "CI must block failing tests"
  - mapped to `.github/workflows/backend-tests.yml`
  - mapped to `main/backend/tests/README.md`
- C line Must: "request_id/trace_id + SLI/SLO + response flow"
  - mapped to rollback drill health checks in `scripts/docker-deploy.sh`
  - mapped to runbook update in `main/ops/README.md`
- D line Must: "SAST/DAST + dependency scan + secret scanning in CI"
  - mapped to `security-check` job in `.github/workflows/backend-tests.yml`
- E line Must: "rollback path can be rehearsed"
  - mapped to `rollback-drill` in `scripts/docker-deploy.sh`

### 3.2 `research_note.md` -> concrete changes
- Quality strategy references (Google/Fowler/pytest/Playwright)
  - mapped to CI layered gate policy update in `main/backend/tests/README.md`
- Observability references (OpenTelemetry/Prometheus/SRE)
  - mapped to health/deep-health checks as minimum rollback acceptance
- Security references (OWASP/SSDF/SLSA)
  - mapped to SAST + dependency + secret scanning workflow gates
- Delivery references (GitHub Actions/DORA/trunk-based)
  - mapped to PR/mainline same blocking quality/security gates

## 4. Verification Commands and Results (R3-4)

Run date: 2026-03-04 (PST)

1. `bash -n scripts/docker-deploy.sh`
- Result: PASS

2. `./scripts/docker-deploy.sh rollback-drill --dry-run`
- Result: PASS

3. `cd main/backend && .venv311/bin/python -m pytest tests/unit/test_gateplus_ci_guard_unittest.py -q`
- Result: PASS

4. `cd main/backend && .venv311/bin/python -m pytest -m "unit and not external" tests/unit/test_gateplus_ci_guard_unittest.py -q`
- Result: PASS

## 5. Changed Files (R3-5)
- `.github/workflows/backend-tests.yml`
- `scripts/docker-deploy.sh`
- `main/backend/tests/README.md`
- `main/ops/README.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/10_B-line-round3-r3-must-minimal-implementation.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/index.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-B-atomic-plan/README.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/main index.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

## 6. Rollback Point
- Use this delivery commit hash as rollback point (reported in final delivery note).
