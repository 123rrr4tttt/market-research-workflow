# Graph Node Standardization Overall Completion (2026-03-03)

## Scope

- A phase: ensemble-level node standardization + graph-specific disjunction projections.
- 数据库图真源阶段（graph_db）：persisted store for nodes and edges, with direct db-primary read path.

## Final Architecture State

1. Read/write flags:
- `GRAPH_NODE_PROJECTION_WRITE_MODE=on`
- `GRAPH_NODE_PROJECTION_READ_MODE=b_primary`
- `GRAPH_NODE_PROJECTION_CANARY_PROJECTS=default,demo_proj`
  - 兼容期说明：运行时仍使用历史配置字面量 `b_primary`，语义统一映射为 `db-primary`（graph_db 真源主路径）。

2. Persisted tables (tenant schema):
- `graph_nodes`
- `graph_node_aliases`
- `graph_edges`

3. Runtime behavior:
- graph APIs read from 数据库图真源主路径（graph_db）.
- no A-edge compatibility fallback.
- writer persists projected nodes + aliases + edges.

## Key Fixes in This Closure

1. Resolved B "no edges" root issue by implementing edge persistence + edge read reconstruction.
2. Removed compatibility fallback that reused A edges when B had no edges.
3. Reduced alias upsert deadlock risk under concurrent shadow/on writes by:
- deterministic alias ordering
- `ON CONFLICT DO NOTHING` for alias records

## Validation Results

Date: 2026-03-03 (PST)

1. Migration
- Alembic head: `20260303_000005`

2. Test gate
- `./scripts/test-standardize.sh ci-pr -q`
- result: `143 passed, 4 skipped, 81 deselected`

3. API smoke (db-primary / graph_db)
- `default/content-graph`: `nodes=195, edges=519`
- `default/market-graph`: `nodes=79, edges=62`
- `default/policy-graph`: `nodes=109, edges=111`
- `demo_proj/content-graph`: `nodes=513, edges=985`
- `demo_proj/market-graph`: `nodes=399, edges=543`
- `demo_proj/policy-graph`: `nodes=510, edges=581`

## Notes

- `default` is currently a data-bearing schema but not an active record in `public.projects`; this does not block graph API reads/writes by `project_key=default`.
- The vector-extension warning on startup is an existing environment concern and does not block graph standardization acceptance.

## Conclusion

Graph node standardization A + graph_db is completed for current backend scope, with graph_db as primary read path and persisted edges enabled.
