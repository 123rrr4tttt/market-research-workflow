# Wave12 Graph Live Smoke Readiness Gate (2026-05-22)

Status: `readiness gate landed / live backend-data visual smoke remains open`.

This Wave12 worker adds a bounded readiness gate for the graph 3D live-smoke gap. It does not claim live DB closure or production visual closure.

## Evidence Added

- `main/backend/app/services/graph/persistence/graph_live_smoke_readiness.py`
  - adds `graph.live_smoke_readiness.v1`;
  - classifies `no_db_fixture_smoke`, `pre_live_db_dry_run_readiness`, `live_db_backend_data_smoke`, and `frontend_backend_data_visual_smoke`;
  - keeps `closure_claim=false` even when optional evidence payloads validate both live stages.
- `main/backend/scripts/check_graph_live_smoke_readiness.py`
  - reuses the existing projection fixture and pre-live DB readiness checks;
  - statically checks GraphPage force3d/debug hooks, GraphPage backend-data query wrappers, and admin graph backend-data routes;
  - emits live DB as `configured_not_run` and frontend/backend-data as `ready_not_run` when no live evidence JSON is supplied.
- `main/backend/tests/unit/test_graph_live_smoke_readiness_unittest.py`
  - proves the configured-but-not-run live DB stage remains non-closing;
  - proves frontend static failures are isolated from no-DB and live DB stage classification;
  - proves incomplete live evidence cannot mark live DB validated.

## Current Gate Output

Command:

```bash
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_live_smoke_readiness.py --format text
```

Observed status:

```text
status=ok
closure_claim=False
live_db_validated=False
frontend_backend_data_smoke_validated=False
no_db_fixture_smoke=passed
pre_live_db_dry_run_readiness=ready
live_db_backend_data_smoke=configured_not_run
frontend_backend_data_visual_smoke=ready_not_run
```

## Remaining Topic Gap

- Live backend-data GraphPage smoke was not run.
- No nonblank force3d canvas proof from live backend graph data was captured.
- `window.__graph3dDebug` scene stats are still proven only by mocked GraphPage e2e and static checker coverage in this branch.

Do not archive this topic from this slice. The next closure slice needs a live backend GraphPage run with nonempty graph endpoint data and captured force3d scene/canvas evidence.
