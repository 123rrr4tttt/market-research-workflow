# Frontend Modern API + Graph Atomic Execution (2026-03-05)

## Scope
- Repo: `main/frontend-modern`
- Focus: API layering, query key standardization, graph computation layering
- Constraint: no feature regression

## Executed Atomic Tasks
1. API domain split (facade-compatible)
- Added:
  - `src/lib/api/domains/project-admin.ts`
  - `src/lib/api/domains/graph-workflow.ts`
  - `src/lib/api/domains/resource-source.ts`
- Updated:
  - `src/lib/api.ts` as stable re-export facade

2. API defect fix
- Fixed duplicated `page_size` query assembly in resource URL filter path:
  - `listResourcePoolUrlsWithFilters` in `resource-source.ts`

3. Query key standardization
- Extended `src/lib/queryKeys.ts` for:
  - dashboard/policy/workflow/resource/admin/crawler/catalog/settings/graph/sourceLibrary/process-by-project
- Replaced literal `queryKey` / `invalidateQueries` usages across major pages and hooks.

4. Graph layering (minimal invasive)
- Added visual-state hook:
  - `src/pages/graph/hooks/useGraphVisualState.ts`
- Added topology/domain pure functions:
  - `src/pages/graph/domain/topology.ts`
    - `computeVisibleSubgraph`
    - `computePageRank`
    - `computeCoreNumber`
    - `collectFocusNodeKeys`
- `GraphPage.tsx` switched to imported domain functions/hooks.

## Gate Verification
- Build:
  - `cd main/frontend-modern && npm run build`
  - Result: passed
- E2E smoke:
  - `npm run test:e2e -- tests/e2e/homepage.spec.ts`
  - `npm run test:e2e -- tests/e2e/ingest-single-url.spec.ts`
  - Result: all passed

## Non-Goal / Remaining
- Deep interaction split in `GraphPage` (selection/hover/node-card state machine extraction) is not completed in this batch.
- Performance warnings remain (large chunks / circular chunk warning), not a functional blocker.

