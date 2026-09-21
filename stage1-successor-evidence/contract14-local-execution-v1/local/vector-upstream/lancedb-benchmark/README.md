# LanceDB Local Index Benchmark Quality

- status: `failed`
- generated_at: `2026-09-06T07:15:20.982420+00:00`
- lancedb: `0.24.2`
- pyarrow: `24.0.0`
- db_path: `/var/folders/ww/__28yy2d01n97fff8jhw9yxm0000gn/T/mrw-local-index-lancedb-benchmark-wm393azl`

## Scope

This is a controlled LanceDB benchmark-quality gate for the optional `local_index` adapter. It verifies repeatable ranking behavior and adapter evidence fields without adding LanceDB to default project dependencies.

## Ranking Stability

| mode | case | passed | expected_top_order | stable_top_order | latency_ms_by_repeat |
|---|---|---:|---|---|---|
| keyword | keyword_source_top2 | True | kw-primary, kw-secondary | kw-primary, kw-secondary | 17.51, 1.67, 2.07 |
| vector | vector_source_top2 | False | vec-primary, vec-secondary | vec-primary, vec-secondary | 3.75, 1.74, 1.69 |
| hybrid | hybrid_source_top2 | False | hybrid-primary, hybrid-secondary | hybrid-primary, hybrid-secondary | 4.28, 2.56, 2.38 |

## Filter Guards

| mode | case | passed | returned_chunks | forbidden_chunks |
|---|---|---:|---|---|
| keyword | keyword_project_filter | True | kw-primary, hybrid-primary, kw-foreign-source, hybrid-secondary, kw-secondary | kw-foreign-project |
| vector | vector_project_filter | False | kw-primary, kw-foreign-source, vec-secondary, vec-primary, vec-foreign-source | vec-foreign-project |
| hybrid | hybrid_project_filter | False | kw-primary, hybrid-primary, kw-foreign-source, hybrid-secondary, hybrid-foreign-source | hybrid-foreign-project |

## Runtime Blockers

- none

## Remaining Blockers

- `semantic_embedding_quality_not_proven`: This benchmark uses deterministic vectors to prove LanceDB ranking wiring and stable top-k behavior. It does not prove production embedding model relevance quality.
- `global_vector_contract_not_closed`: Unified vector object schema, embedding model/version provenance, and main search evidence contract alignment remain open in CURRENT_DEV.

## Rerun

```bash
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py --out-dir stage1-successor-evidence/contract14-local-execution-v1/local/vector-upstream/lancedb-benchmark
```

Full JSON evidence is in `benchmark_quality_results.json`.
