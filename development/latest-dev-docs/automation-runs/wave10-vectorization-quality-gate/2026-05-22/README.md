# Wave10 Vectorization Quality Gate

- status: `passed`
- contract_version: `wave10-vectorization-quality-gate.v1`
- scope: `deterministic_local_fixture_no_network_no_container_start`

## Deterministic Assertions

- search provider trace keeps local open-search providers explicit-only and provider=auto excludes them
- local_index keyword, vector, and hybrid runtime evidence executed without fallback in captured LanceDB smoke
- benchmark fixture meets deterministic case/repeat thresholds for keyword, vector, and hybrid modes
- benchmark fixture trace includes project/source/top_k and mode fields for all result rows
- vector and hybrid runtime exceptions fall back to keyword with explicit fallback_from and fallback_reason metadata
- fixture benchmark is not treated as production embedding semantic quality evidence

## Evidence Inputs

- search provider trace: `passed`
- local_index runtime smoke: `passed`
- local_index benchmark threshold: `passed`
- local_index fallback contract: `passed`

## Quality Thresholds

- required modes: `keyword, vector, hybrid`
- min ranking cases: `3`
- min filter cases: `3`
- min repeats per ranking case: `3`

## Remaining Gaps

- `current_container_availability_not_replayed`: This gate reads recorded provider evidence and does not start or probe SearXNG/YaCy containers.
- `semantic_embedding_quality_not_proven`: The benchmark fixture uses deterministic vectors and does not prove production embedding relevance quality.
- `global_vector_contract_not_closed`: Unified vector object schema, embedding provenance, and main search evidence contract remain CURRENT_DEV work.

## Rerun

```bash
/Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave10_vectorization_quality_gate.py --out-dir development/latest-dev-docs/automation-runs/wave10-vectorization-quality-gate/2026-05-22
```

Full deterministic output is in `contract_summary.json`.
