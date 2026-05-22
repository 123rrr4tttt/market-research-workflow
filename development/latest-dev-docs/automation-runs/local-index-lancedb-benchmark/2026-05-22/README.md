# LanceDB Local Index Benchmark Quality

- status: `passed`
- generated_at: `2026-05-22T04:49:39.068203+00:00`
- lancedb: `0.24.2`
- pyarrow: `24.0.0`
- db_path: `/var/folders/ww/__28yy2d01n97fff8jhw9yxm0000gn/T/mrw-local-index-lancedb-benchmark-ytr9s5cf`

## Scope

This is a controlled LanceDB benchmark-quality gate for the optional `local_index` adapter. It verifies repeatable ranking behavior and adapter evidence fields without adding LanceDB to default project dependencies.

## Ranking Stability

| mode | case | passed | expected_top_order | stable_top_order | latency_ms_by_repeat |
|---|---|---:|---|---|---|
| keyword | keyword_source_top2 | True | kw-primary, kw-secondary | kw-primary, kw-secondary | 46.23, 6.05, 10.38 |
| vector | vector_source_top2 | True | vec-primary, vec-secondary | vec-primary, vec-secondary | 17.84, 6.97, 6.95 |
| hybrid | hybrid_source_top2 | True | hybrid-primary, hybrid-secondary | hybrid-primary, hybrid-secondary | 44.66, 21.63, 19.25 |

## Filter Guards

| mode | case | passed | returned_chunks | forbidden_chunks |
|---|---|---:|---|---|
| keyword | keyword_project_filter | True | kw-primary, hybrid-primary, kw-foreign-source, hybrid-secondary, kw-secondary | kw-foreign-project |
| vector | vector_project_filter | True | vec-primary, vec-foreign-source, kw-primary, kw-secondary, vec-secondary | vec-foreign-project |
| hybrid | hybrid_project_filter | True | hybrid-primary, hybrid-foreign-source, hybrid-secondary, kw-primary, vec-secondary | hybrid-foreign-project |

## Runtime Blockers

- none

## Remaining Blockers

- `semantic_embedding_quality_not_proven`: This benchmark uses deterministic vectors to prove LanceDB ranking wiring and stable top-k behavior. It does not prove production embedding model relevance quality.
- `global_vector_contract_not_closed`: Unified vector object schema, embedding model/version provenance, and main search evidence contract alignment remain open in CURRENT_DEV.

## Rerun

```bash
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py --out-dir development/latest-dev-docs/automation-runs/local-index-lancedb-benchmark/2026-05-22
```

Full JSON evidence is in `benchmark_quality_results.json`.
