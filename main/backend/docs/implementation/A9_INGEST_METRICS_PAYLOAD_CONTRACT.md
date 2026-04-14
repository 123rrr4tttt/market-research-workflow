# A9 Ingest Metrics Payload Contract

## Scope

- Ingest frontdoor output only (`single_url`, `url_pool`).
- Local per-task metrics only (no global aggregation service).

## Stable Payload Schema (`metrics_payload`)

```json
{
  "schema_version": "a9.v1",
  "window": "task_local",
  "sample_size": 0,
  "url_only_document_rate": 0.0,
  "empty_body_rate": 0.0,
  "reason_code_top_n": [
    {"reason_code": "ok", "count": 0, "rate": 0.0}
  ],
  "adapter_hit_rate": [
    {"adapter": "single_url", "count": 0, "rate": 0.0}
  ],
  "counters": {
    "total_samples": 0,
    "url_only_documents": 0,
    "empty_body_documents": 0
  }
}
```

Required stable fields:

- `url_only_document_rate`
- `empty_body_rate`
- `reason_code_top_n`
- `adapter_hit_rate`

## Output Placement

- `single_url` result:
  - `result.meta.metrics_payload`
  - `result.debug.metrics_payload`
- `url_pool` result:
  - `result.meta.metrics_payload`
  - `result.debug.metrics_payload`

This placement keeps compatibility with current result shape while exposing a single canonical payload object in both `meta` and `debug`.
