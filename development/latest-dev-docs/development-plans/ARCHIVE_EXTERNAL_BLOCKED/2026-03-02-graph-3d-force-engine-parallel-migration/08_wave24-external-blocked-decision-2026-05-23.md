# Wave24 Graph 3D External Blocked Decision

- Date: 2026-05-23
- Status: `external_blocked`
- Previous CURRENT_DEV status: `partial`
- Decision: migrate out of `CURRENT_DEV` into `ARCHIVE_EXTERNAL_BLOCKED`

## Decision

The Graph 3D Force Engine migration is no longer a repo-local implementation blocker. The repository now has deterministic gates for the backend projection contract, the Force3D frontend contract, runtime pixel/shape framing, rollback/readback, and visual data smoke boundaries.

It is not marked `closed`, because the remaining acceptance requires configured live tenant DB data and browser/WebGL evidence that cannot be proven by repo-local fixtures alone.

## Repo-Local Evidence

- `main/backend/scripts/check_graph_live_smoke_readiness.py`
- `main/backend/scripts/check_graph_visual_data_smoke_gate.py`
- `main/backend/scripts/check_graph_rollout_readback_gate.py`
- `main/frontend-modern/scripts/check_graph_force3d_frontend_contract.mjs`
- `main/frontend-modern/package.json` `check:graph-runtime-pixel-gate`
- `main/backend/tests/unit/test_graph_rollout_readback_gate_unittest.py`
- `main/backend/tests/unit/test_graph_live_smoke_readiness_unittest.py`
- `main/backend/tests/unit/test_graph_visual_data_smoke_gate_unittest.py`

## External Blockers

- Run GraphPage against configured tenant DB data and real backend graph endpoints.
- Capture a nonblank WebGL canvas using backend graph data, not mocked graph data.
- Capture `window.__graph3dDebug` scene-node and visibility stats from the live browser run.
- Store the live tenant DB / WebGL smoke artifact before any full closure claim.

## Verification

```bash
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_rollout_readback_gate.py --format text
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_live_smoke_readiness.py --format text
/Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_graph_visual_data_smoke_gate.py --format text
npm --prefix main/frontend-modern run check:graph-force3d-frontend-contract
npm --prefix main/frontend-modern run check:graph-runtime-pixel-gate
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_graph_rollout_readback_gate_unittest.py main/backend/tests/unit/test_graph_live_smoke_readiness_unittest.py main/backend/tests/unit/test_graph_visual_data_smoke_gate_unittest.py
```
