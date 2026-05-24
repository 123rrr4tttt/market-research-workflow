# Wave55 OSS Node Platform IO Live SLA Readback

- Status: `platform_io_live_sla_validated`
- Decision date: 2026-05-23
- Evidence: [wave29-oss-node-vector-manifest-replay/2026-05-23](../../../automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23/README.md)
- Checker: `ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py`
- Unit gate: `main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py`
- Shared/global indexes edited: `false`

## Result

Wave55 extends the Wave29 checker with a platform IO SLA readback layer.

The live run used the local backend at `http://127.0.0.1:8000/api/v1` and the local frontend at `http://127.0.0.1:5173/`. It compiled a workflow graph, ran a `vector_search` node under project scope `wave55_oss_node_platform_io`, read back the run detail, event stream, stateful replay, compiled graph, and frontend root asset, then verified the frontend workflow client bindings.

The checker now records:

- `platform_io_live_sla_closed=true`
- `closed_condition=live_scheduler_tenant_db_ui_sla_not_proven`
- live compile/run/get-run/get-events/stateful-replay/get-compiled envelopes all returned `status=ok`
- live replay consistency returned `true`
- frontend workflow API client and LLM designer consumer markers are present

## Remaining External Conditions

This closes the scheduler / tenant DB / UI SLA condition for this target. It does not close:

- `external_embedding_provider_live_not_verified`
- `local_open_search_live_quality_not_sealed`
- `semantic_embedding_quality_not_proven`

Those provider and quality conditions remain visible in the provider manifest and node trace output.

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23 --live-api-base http://127.0.0.1:8000/api/v1 --live-ui-base http://127.0.0.1:5173/ --live-probe-timeout 5
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py
```
