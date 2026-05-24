# Wave57 OSS Node Public-Corpus Semantic Relevance Gate

- Status: `target_local_provider_quality_closed`
- Decision date: 2026-05-23 PDT
- Evidence: [wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23](../../../automation-runs/wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23/README.md)
- Checker: `ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py`
- Unit gate: `main/backend/tests/unit/test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.py`
- Shared/global indexes edited: `false`

## Result

Wave57 attaches the missing public-corpus semantic relevance evidence for the OSS-node provider-quality blocker.

The gate reads back the Wave55 OSS-node search-quality artifact, verifies the checked-in public OSS corpus index, then evaluates deterministic semantic relevance over fixed excerpts from:

- `reference-pool/oss/dify/README.md`
- `reference-pool/oss/n8n/README.md`
- `reference-pool/oss/langflow/README.md`
- `reference-pool/oss/outline/README.md`
- `reference-pool/oss/silverbullet-ai/README.md`
- `reference-pool/oss/agent-cases/langgraph/README.md`
- `reference-pool/oss/temporal/README.md`

The quality readback records:

- `status=passed`
- `public_source_count=7`
- `domain_count=7`
- `case_count=7`
- `top1_accuracy=1.0`
- `recall_at_3=1.0`
- `mrr=1.0`
- `min_top2_margin=0.061205`
- `min_hard_negative_margin=0.061205`
- `retrieval_contracts.status=passed`

## Closure Decision

Target-local decision: `closed_candidate`.

Closed by this gate:

- `oss_node_provider_quality`
- `public_corpus_semantic_relevance_not_attached`
- `production_semantic_embedding_quality_not_proven` in this target's public-corpus route

The artifact reports `remaining_conditions=[]` and `target_archive_closed_candidate=true`.

This document does not move the directory to `ARCHIVE_CLOSED` and does not update the global external-blocker manifest or global indexes. That sync remains a supervisor/global navigation step outside this task's scope.

## Non-Claimed Scope

Wave57 does not start or rank live SearXNG / YaCy containers. It also does not claim generic production live-traffic vector quality outside this target-local public-corpus route.

The artifact keeps those boundaries explicit:

- `live_container_quality_claim_allowed=false`
- `production_traffic_quality_claim_allowed=false`
- `non_claimed_scope=["local_open_search_live_container_quality_not_replayed", "generic_production_live_traffic_vector_quality"]`

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py --out-dir development/latest-dev-docs/automation-runs/wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.py
```
