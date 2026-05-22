# Wave18 Open Search Health Artifact

日期：2026-05-22 PST

## Scope

- Providers: `searxng`, `yacy`.
- Checker: `main/backend/scripts/check_open_search_health_artifact.py`.
- Artifact: `open_search_health_artifact.json`.
- Inputs: Wave12 provider readiness summary, Wave15 runtime boundary checker, launcher settings, Docker compose surfaces, and backend search-provider code.

## Result

- Status: `passed`.
- Health state: `partial`.
- Live probe open: `true`.
- Closure claim allowed: `false`.
- Provider auto promotion allowed: `false`.
- Docker service status collection: Docker daemon was unavailable in this run, so compose status is recorded as `unknown` instead of being inferred as running.

| provider | endpoint | current boundary | live status | service_not_started_connect_error | closure claim |
|---|---|---|---|---:|---:|
| `searxng` | `http://127.0.0.1:8088` | `service_not_started_connect_error` | `unavailable` | true | false |
| `yacy` | `http://127.0.0.1:8090` | `service_not_started_connect_error` | `unavailable` | true | false |

## Evidence Semantics

- The checker does not start Docker services.
- `status=passed` means endpoint wiring, compose expectations, explicit provider routing, current service-status capture, and no-closure facts are machine-checkable.
- `status=passed` does not mean SearXNG or YaCy live availability is closed.
- A running or responding endpoint would still be recorded as `live_query_unsealed`, not as provider quality closure or `provider=auto` promotion.

## Re-run Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_open_search_health_artifact.py --probe-timeout 0.2 --write-output development/latest-dev-docs/automation-runs/wave18-open-search-health-artifact/2026-05-22/open_search_health_artifact.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_open_search_health_artifact_unittest.py
```
