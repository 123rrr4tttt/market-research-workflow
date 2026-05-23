# Wave29 OSS Node Vector Manifest Replay

- status: `passed`
- contract_version: `wave29-oss-node-vector-manifest-replay.v1`
- scope: `oss_node_vector_manifest_fixture_replay_no_live_provider_no_tenant_runtime`
- archive_external_blocked_candidate: `true`

## Node Replay Matrix

| mode | status | provider_id | manifest_consumed | closure_claim_allowed | live_provider_verified | semantic_quality_claim_allowed |
|---|---|---|---:|---:|---:|---:|
| keyword | `passed` | `local_index.keyword` | true | false | false | false |
| vector | `passed` | `local_index.vector` | true | false | false | false |
| hybrid | `passed` | `local_index.hybrid` | true | false | false | false |

## Repo-Local Blockers Closed

- `node_schema_runtime_persistence_platformization_scope_not_closed`
- `vector_search_node_manifest_consumption_not_live_replayed`

## External Conditions Retained

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`
- `live_scheduler_tenant_db_ui_sla_not_proven`

## Gate Semantics

- status passed means: the workflow graph compiler, node runtime, normalized result envelope, event log, and event replay can consume all keyword/vector/hybrid provider manifest rows while preserving unsupported closure claims
- status passed does not mean: external embedding providers, local open-search live quality, semantic relevance, tenant DB persistence, scheduler SLA, or browser UI SLA are closed

## Rerun

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py
```

Full deterministic output is in `oss_node_vector_manifest_replay.json`.
