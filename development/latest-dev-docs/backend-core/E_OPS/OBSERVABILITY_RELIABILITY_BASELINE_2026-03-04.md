# Observability and Reliability Baseline (C-Line Must)

Date: 2026-03-04 (PST)  
Scope: `main/backend` critical user journeys

## 1. Must-first rollout boundary

- Keep current lightweight runtime stack; no new heavy dependency.
- Prioritize observability on critical path first:
  - Request context trace continuity (`request_id` / `trace_id`)
  - Health and core API availability
  - Alert routing and on-call ownership

## 2. Core user journeys (minimum set)

1. Journey-A: `GET /api/v1/health` and `GET /api/v1/health/deep`
2. Journey-B: `POST /api/v1/ingest/commodity/metrics` (sync/async entry)
3. Journey-C: `GET /api/v1/process/stats` (process status visibility)

## 3. SLI and SLO baseline

| Journey | SLI | SLO (initial) | Source |
|---|---|---|---|
| A | availability (2xx ratio) | >= 99.9% / 30d | Prometheus + health probe |
| A | latency p95 | <= 300ms / 24h | `market_api_request_latency_seconds` |
| B | request success ratio | >= 99.0% / 7d | API status code + task status |
| B | async task start success | >= 99.5% / 7d | enqueue result / error code |
| C | freshness | process stats delay <= 5 min | stats timestamp delta |

Notes:
- SLO targets are bootstrap values for current stage and can be tightened after two release cycles.
- For non-prod environments, track trend first and do not hard-page on transient failures.

## 4. Alert severity and paging

| Severity | Trigger example | Action window | On-call action |
|---|---|---|---|
| P1 | Journey-A availability < 99.0% in rolling 10m, or health endpoint fully unavailable | immediate | page primary on-call, escalate to backup in 10m |
| P2 | Journey-B success ratio < 98.0% in rolling 30m | 30m | on-call investigates and mitigates; create incident record |
| P3 | latency/freshness trend regression without hard outage | 1 business day | create ticket, schedule fix in next sprint |

## 5. On-call process (minimal runbook)

1. Detect: alert fires from Prometheus/Grafana rule and includes `request_id`/`trace_id` sample.
2. Triage: determine scope (single endpoint vs platform-wide), severity (P1/P2/P3), and blast radius.
3. Mitigate:
   - P1: restore service first (rollback/restart/degrade mode), then root-cause.
   - P2/P3: isolate failing dependency, apply guardrail/fallback, monitor recovery trend.
4. Escalate:
   - P1: page backup on-call after 10 minutes if unresolved.
   - P2: escalate to module owner after 30 minutes if unresolved.
5. Recover and close:
   - record start/end time, impact, action, and rollback point
   - publish postmortem within 24 hours for P1, 3 business days for P2

## 6. Minimum dashboard and rule checklist

- Dashboard panels:
  - API availability by endpoint
  - p95 latency by endpoint
  - error rate by endpoint/status
  - deep health component status (DB/Elasticsearch)
- Rules:
  - `health_unavailable`
  - `high_error_rate_ingest`
  - `latency_regression_p95`
  - `process_stats_staleness`

## 7. Implementation status

- [x] Request context trace continuity skeleton (`X-Trace-Id`, `traceparent` fallback).
- [x] Baseline SLI/SLO and alerting/on-call documentation.
- [x] Integration guard for error envelope trace continuity (`traceparent` -> `meta.trace_id` + `X-Trace-Id`).
- [ ] Grafana dashboard JSON provisioning (optional next step).
- [ ] Dedicated alertmanager route matrix (optional next step).

## 8. R4 continuation verification snapshot (2026-03-04 PST)

- Gate command:
  - `bash scripts/pre_release_pipeline.sh`
- Result:
  - pipeline pass, artifacts generated under
    `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/artifacts/pre-release-round4/`
  - `gate-result.json`: `pass`
  - `observability-check.json`: `pass`
- Environment note:
  - Local default `python3` is 3.9; direct `pytest` collection for `tests/e2e/test_request_context_headers_e2e.py`
    requires Python 3.10+ runtime compatibility for `str | None` annotations.
