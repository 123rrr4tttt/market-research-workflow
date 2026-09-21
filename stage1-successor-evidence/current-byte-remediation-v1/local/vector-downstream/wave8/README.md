# Wave8 Search / Vectorization Contract

- status: `failed`
- contract_version: `wave8-search-vectorization-runtime-contract.v1`
- scope: `deterministic_reuse_no_network_no_container_start`

## Evidence Inputs

- search provider trace: `passed`
- search provider container replay: `missing` (captured artifact only)
- local_index runtime smoke: `passed`
- local_index benchmark: `passed`

## Remaining Gaps

- `current_container_availability_not_replayed`: This deterministic gate reads recorded replay evidence and does not start or probe SearXNG/YaCy containers.
- `semantic_embedding_quality_not_proven`: LanceDB benchmark uses deterministic vectors and does not prove production embedding relevance quality.
- `global_vector_contract_not_closed`: Unified vector object schema, embedding model provenance, and main search evidence contract remain CURRENT_DEV work.

## Rerun

```bash
/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python ops/search-lab/scripts/wave8_search_vectorization_contract.py --out-dir stage1-successor-evidence/current-byte-remediation-v1/local/vector-downstream/wave8
```

Full deterministic output is in `contract_summary.json`.
