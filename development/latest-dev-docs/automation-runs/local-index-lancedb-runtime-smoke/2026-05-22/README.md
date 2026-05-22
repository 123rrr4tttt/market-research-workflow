# LanceDB Local Index Runtime Smoke

- status: `passed`
- generated_at: `2026-05-22T04:15:57.810050+00:00`
- lancedb: `0.24.2`
- pyarrow: `24.0.0`
- db_path: `/var/folders/ww/__28yy2d01n97fff8jhw9yxm0000gn/T/mrw-local-index-lancedb-runtime-duaqzn83`

## Mode Evidence

| mode | executed_mode | top_chunk_id | top_source_id | top_k | latency_ms |
|---|---|---|---|---:|---:|
| keyword | keyword | chunk-keyword | source-keyword | 1 | 65.33 |
| vector | vector | chunk-vector | source-vector | 1 | 30.86 |
| hybrid | hybrid | chunk-hybrid | source-hybrid | 1 | 41.27 |

## Blockers

- none

## Rerun

```bash
main/backend/.venv311/bin/python ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py --out-dir development/latest-dev-docs/automation-runs/local-index-lancedb-runtime-smoke/2026-05-22
```

Full JSON evidence is in `runtime_smoke_results.json`.
