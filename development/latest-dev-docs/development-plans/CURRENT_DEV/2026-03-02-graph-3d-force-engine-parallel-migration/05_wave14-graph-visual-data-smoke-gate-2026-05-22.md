# Wave14 Graph Visual Data Smoke Gate (2026-05-22)

Status: `repo gate landed / backend-data and live UI visual smokes remain explicitly non-closing unless evidence is supplied`.

This Wave14 worker adds a narrow Graph 3D visual-data boundary gate. It separates three proof levels so fixture data cannot be mistaken for backend-data visual validation, and backend-data payload validation cannot be mistaken for live UI force3d closure.

## Evidence Added

- `main/backend/scripts/check_graph_visual_data_smoke_gate.py`
  - adds `graph.visual_data_smoke_gate.v1`;
  - validates a deterministic fixture visual payload with nonempty nodes/edges and resolved edge endpoints;
  - checks that admin graph backend-data routes, frontend API wrappers, and GraphPage force3d data mapping still exist;
  - records backend-data visual smoke as `ready_not_run` until explicit live backend endpoint payload evidence is supplied;
  - records live UI force3d smoke as `not_run` or `ready_not_run` until explicit browser/canvas/debug evidence is supplied;
  - always emits `closure_claim=false`.
- `main/backend/tests/unit/test_graph_visual_data_smoke_gate_unittest.py`
  - proves the default gate is `partial`;
  - proves backend-data visual payload evidence does not stand in for live UI force3d smoke;
  - proves complete live UI evidence can be recorded without claiming topic closure;
  - proves incomplete backend-data evidence fails instead of being accepted as partial success.

## Current Gate Output

Command:

```bash
python3 main/backend/scripts/check_graph_visual_data_smoke_gate.py --format text
```

Observed status:

```text
status=passed
readiness_state=partial
closure_claim=False
partial/live-smoke boundary: fixture visual data smoke is deterministic; backend-data visual smoke=ready_not_run; live UI smoke=not_run; closure_claim=false unless a separate supervisor closure gate archives the topic
fixture_visual_data_smoke=validated passed=True validated=True
backend_data_visual_smoke=ready_not_run passed=True validated=False
live_ui_force3d_smoke=not_run passed=True validated=False
```

## Boundary

- `fixture_visual_data_smoke`: repo-local deterministic payload only.
- `backend_data_visual_smoke`: requires live backend graph endpoint payload evidence with nonempty nodes/edges and schema version.
- `live_ui_force3d_smoke`: requires GraphPage/browser evidence from backend data, including nonblank canvas and `window.__graph3dDebug` visibility stats.

This worker does not archive the Graph 3D Force Engine migration topic. The remaining closure work is a live backend GraphPage run with nonempty graph endpoint data and captured force3d scene/canvas evidence.
