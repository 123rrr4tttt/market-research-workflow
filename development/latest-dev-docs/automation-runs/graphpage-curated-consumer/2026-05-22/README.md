# GraphPage Curated Consumer Evidence (2026-05-22)

- Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/graphpage-curated-consumer`
- Branch: `codex/devdocs-wave4-graphpage-curated-consumer`

## Result

Status: `partial closure / first UI consumer landed`.

GraphPage builder mode now exposes a curated workflow-graph bridge in the local draft editor. The UI can:

1. save the current local draft to `POST /api/v1/workflow-graph/curated/{graph_id}/draft`;
2. submit the same draft through `POST /api/v1/workflow-graph/curated/{graph_id}/submit`;
3. sync a server snapshot back through `POST /api/v1/workflow-graph/curated/{graph_id}/sync`.

The implementation keeps the existing admin graph endpoints as the visible graph data source. It does not switch all GraphPage rendering to curated storage because the existing business graph payload may contain cycles and broad legacy fields that curated submit rejects.

## Contract Anchors

- GraphPage UI bridge: `main/frontend-modern/src/pages/GraphPage.tsx`
- API client: `main/frontend-modern/src/lib/api/domains/graph-workflow.ts`
- Endpoint map: `main/frontend-modern/src/lib/api/endpoints.ts`
- E2E proof: `main/frontend-modern/tests/e2e/graphpage.spec.ts`

## Proven Fields

The focused e2e proves that GraphPage builder mode serializes local draft nodes and edges into curated DSL fields:

- node aliases: `id`, `type`, `node_id`, `node_type`
- edge aliases: `from_node_id`, `to_node_id`, `edge_type`, `from`, `to`
- submit metadata: `actor_id`, `base_revision`, `object_scope`

## Validation

See [`validation.json`](./validation.json).

## Remaining Risk

- This is a narrow UI consumer, not a full GraphPage data-source migration.
- Curated submit still blocks temporary node ids (`draft-`, `tmp-`, `temp-`) and cyclic graphs.
- GraphPage reporting/writing handoff buttons are still not exposed in this lane; backend handoff remains proven by the Wave3 API route evidence.
