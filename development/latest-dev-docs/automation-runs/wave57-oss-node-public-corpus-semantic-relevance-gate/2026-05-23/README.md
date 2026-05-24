# Wave57 OSS Node Public-Corpus Semantic Relevance Gate

- status: `passed`
- contract_version: `wave57-oss-node-public-corpus-semantic-relevance-gate.v1`
- scope: `target_local_public_oss_corpus_semantic_relevance_no_network_no_live_container`
- public_corpus_semantic_relevance_claim_allowed: `true`
- live_container_quality_claim_allowed: `false`
- target_archive_closed_candidate: `true`

## Public Corpus

- source_index: `reference-pool/oss/INDEX.md`
- source_count: `7`
- evaluated repos: `dify`, `n8n`, `langflow`, `outline`, `silverbullet-ai`, `langgraph`, `temporal`

## Quality Metrics

- domains: `7`
- cases: `7`
- top1_accuracy: `1.0`
- recall_at_3: `1.0`
- mrr: `1.0`
- min_top2_margin: `0.061205`
- min_hard_negative_margin: `0.061205`

## Decision

- closed conditions: `oss_node_provider_quality`, `public_corpus_semantic_relevance_not_attached`, `production_semantic_embedding_quality_not_proven`
- remaining conditions: `none`
- non-claimed scope: `local_open_search_live_container_quality_not_replayed`, `generic_production_live_traffic_vector_quality`

## Rerun

```bash
PYTHONPATH=main/backend python3 ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py --out-dir development/latest-dev-docs/automation-runs/wave57-oss-node-public-corpus-semantic-relevance-gate/2026-05-23
PYTHONPATH=main/backend python3 -m pytest -q main/backend/tests/unit/test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.py
```

Full deterministic output is in `oss_node_public_corpus_semantic_relevance_gate.json`.
