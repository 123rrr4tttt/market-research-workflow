# A-line Round7 Flaky Trend Closure (2026-05-23)

Status: `closed / wave39_verified`

## Scope

This closes the repo-local Round7 work recorded in
`14_A-line-round7-mvp-machine-readable-flake-trend-summary-2026-03-04.md`.

The closed requirement is the minimal machine-readable flaky-trend chain:

- `main/backend/scripts/flake_trend.py` exposes `build_summary(...)`.
- `--output-json` is optional and writes a stable JSON summary when present.
- The JSON keeps CI compatibility through `tests` and adds the documented
  `totals / threshold / top_n / items` fields.
- Flaky observation and registry validation scripts have unit coverage.

## Code Landed

- `main/backend/scripts/flake_trend.py`
  - added `build_summary(...)`;
  - made `--output-json` optional;
  - kept the existing CI `tests` schema for `check_flake_trend_thresholds.py`.
- `main/backend/scripts/flake_report.py`
  - fixed failure/error extraction so failed testcase names are emitted.
- `main/backend/tests/unit/test_flake_trend_unittest.py`
  - covers the machine-readable summary schema and optional JSON output.
- `main/backend/tests/unit/test_flake_report_unittest.py`
  - covers failed testcase reporting.
- `main/backend/tests/unit/test_validate_flaky_registry_unittest.py`
  - covers pass/fail ownership validation.

## Validation

Run from the repository root:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/unit/test_flake_trend_unittest.py \
  tests/unit/test_flake_report_unittest.py \
  tests/unit/test_validate_flaky_registry_unittest.py
```

Observed: `6 passed`.

## Remaining Boundary

This closure does not change the flaky threshold policy. It only closes the
machine-readable report and unit-test evidence gap for Round7.
