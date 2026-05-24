# Wave29 OSS Node Vector Manifest Replay

- status: `passed`
- contract_version: `wave29-oss-node-vector-manifest-replay.v1`
- scope: `oss_node_vector_manifest_replay_with_wave55_platform_io_sla_readback`
- archive_external_blocked_candidate: `true`
- platform_io_live_sla_closed: `true`

## Node Replay Matrix

| mode | status | provider_id | manifest_consumed | closure_claim_allowed | live_provider_verified | semantic_quality_claim_allowed |
|---|---|---|---:|---:|---:|---:|
| keyword | `passed` | `local_index.keyword` | true | false | false | false |
| vector | `passed` | `local_index.vector` | true | false | false | false |
| hybrid | `passed` | `local_index.hybrid` | true | false | false | false |

## Repo-Local Blockers Closed

- `node_schema_runtime_persistence_platformization_scope_not_closed`
- `vector_search_node_manifest_consumption_not_live_replayed`

## Wave55 Platform IO SLA Readback

- contract_version: `wave55-oss-node-platform-io-sla-readback.v1`
- status: `passed`
- repo_local_contract: `passed`
- live_probe: `passed`
- live_probe_requested: `true`
- platform_io_live_sla_closed: `true`
- closure_position: `scheduler_tenant_db_ui_live_sla_validated`

## External Conditions Retained

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`

## Gate Semantics

- status passed means: the workflow graph compiler, node runtime, normalized result envelope, event log, event replay, tenant project-scope IO trace, workflow API envelope, and frontend workflow client binding can consume all keyword/vector/hybrid provider manifest rows; when live API/UI bases are supplied, the live workflow run/readback/UI asset probe also passed
- status passed does not mean: external embedding provider quality, local open-search relevance, or production semantic quality are closed; if live API/UI bases were omitted, scheduler/tenant DB/UI live SLA closure is not claimed

## Rerun

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23 --live-api-base http://127.0.0.1:8000/api/v1 --live-ui-base http://127.0.0.1:5173/
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py
```

Full deterministic output is in `oss_node_vector_manifest_replay.json`.
