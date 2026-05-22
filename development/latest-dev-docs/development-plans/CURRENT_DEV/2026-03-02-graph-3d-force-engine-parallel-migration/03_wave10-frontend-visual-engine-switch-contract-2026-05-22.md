# Wave10 Frontend Visual / Engine-Switch Contract Evidence (2026-05-22)

Status: `narrow frontend visual contract added / topic remains CURRENT_DEV`.

This Wave10 worker adds a repo-repeatable guard for the Graph 3D frontend visual surface. It does not claim full topic closure, because this slice still uses mocked GraphPage data and does not prove a real backend data visual smoke.

## Implemented Slice

- Added `main/frontend-modern/scripts/check_graph_force3d_frontend_contract.mjs`.
  - Checks that `react-force-graph-3d` remains declared.
  - Checks the GraphPage force3d render boundary, loader retry, engine-switch guard, viewport sync, debug hook, fallback text, canvas host test id, and CSS host/canvas rules.
  - Checks the focused E2E coverage names and force3d/legacy/fallback probes.
- Added `check:graph-force3d-frontend-contract` to `main/frontend-modern/package.json`.
- Extended `main/frontend-modern/tests/e2e/graphpage.spec.ts` with `graph page survives rapid 3D engine switch with viewport evidence or fallback`.
  - The test enters 3D mode, rapidly switches the projection engine, and accepts one of three safe states:
    - force3d canvas host with nonzero viewport/canvas dimensions and debug scene-node stats;
    - automatic legacy fallback with visible viewport;
    - stable legacy viewport after the switch guard coalesces rapid changes.

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave10-graph-frontend-visual`:

```bash
npm --prefix main/frontend-modern ci
npm --prefix main/frontend-modern run check:graph-force3d-frontend-contract
npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts --reporter=line --workers=1
npm --prefix main/frontend-modern run lint
```

Results:

- `check:graph-force3d-frontend-contract`: passed.
- `tests/e2e/graphpage.spec.ts --workers=1`: passed, `5 passed (17.3s)`.
- `lint`: passed.
- `npm ci`: completed; npm reported two moderate vulnerabilities from the existing frontend dependency tree. No dependency remediation was attempted in this graph frontend worker.

Observed but not used as a pass gate:

- A default parallel Playwright run (`tests/e2e/graphpage.spec.ts --reporter=line`) produced `3 passed / 2 failed` under five workers.
- The two failures were existing GraphPage spec timing/isolation symptoms: one smoke assertion timed out around the late `3D模式` render, and the curated panel assertion timed out while the page was still in its loading/draft-empty state. The single-worker replay passed the same spec.

## Closure Impact

This narrows the remaining frontend visual closure gap by making the force3d route, fallback route, viewport sync, and engine-switch guard checkable in-repo.

Retained blockers before this topic can be archived:

- no branch-local real backend data visual smoke was run;
- no production WebGL nonblank smoke with real graph data was added in this slice;
- default fully parallel GraphPage E2E still shows timing/isolation sensitivity and should not be treated as a clean closure gate until stabilized.
