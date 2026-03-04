# R5 Reference-Pool Proxy Mapping (Repo F)

Date: 2026-03-04 (PST)
Scope: `llm-report` R5 incremental hardening

## Detection Result
- `docs/reference-pool` latest batch was not present before this run.
- This file acts as a proxy mapping batch for R5, built from the newest relevant docs in:
  - `development/latest-dev-docs`
  - `main/backend/docs`

## Assumptions
1. "Latest" uses both filename date and filesystem mtime.
2. When `docs/reference-pool` batch is missing, `development/latest-dev-docs` + `main/backend/docs` are accepted as proxy inputs.
3. R5 for F line is constrained to minimal, rollback-friendly increments on governance/gate/observability without breaking existing API behavior.

## Latest Inputs (evidence)
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-sa3-r3-f-llm-report-must-minset/01_sa3-r3-f-implementation-2026-03-04.md` (mtime: 2026-03-04 00:21:24 PST)
- `main/backend/docs/version-F-llm-report-delivery-2026-03-03.md` (mtime: 2026-03-04 00:23:28 PST)
- `main/backend/docs/AI_GOVERNANCE_MIN_BASELINE.md` (mtime: 2026-03-04 00:16:32 PST)
- `development/latest-dev-docs/README.md` (mtime: 2026-03-04 00:20:45 PST)
- `development/latest-dev-docs/MERGED_OVERVIEW.md` (mtime: 2026-03-04 00:20:51 PST)
- `development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md` (mtime: 2026-03-03 23:16:44 PST)

## Repo-Level Mapping
- Governance baseline -> `main/backend/docs/AI_GOVERNANCE_MIN_BASELINE.md`
- LLM report delivery contract -> `main/backend/docs/version-F-llm-report-delivery-2026-03-03.md`
- API gate behavior + job traceability -> `main/backend/app/api/llm_report.py`
- Gate evaluation and observability fields -> `main/backend/app/services/llm_report_generator.py`
- Gate switch config -> `main/backend/app/settings/config.py`
- Regression gate checks ->
  - `main/backend/tests/unit/test_llm_report_api_unittest.py`
  - `main/backend/tests/unit/test_llm_report_generator_unittest.py`
  - `main/backend/scripts/check_llm_report_must_minset.py`

## R5 Increment Focus from Mapping
- Security hardening: safer markdown rendering for user-controlled text.
- Observability hardening: expose `job_id` and gate-mode fallback metadata in API response and job payload.
- Gate reliability: preserve existing strict/warn/off behavior while making fallback state explicit.
