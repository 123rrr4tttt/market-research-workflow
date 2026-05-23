# Wave45 Manual Structured Consumer Live API Closure (2026-05-23)

Status: `passed`.

## Scope

This run resolves the shared external blocker `live_db_api_smoke_not_run` for:

- `2026-03-12-data-structured-service-modularization`
- `2026-03-14-consumer-side-modularization`

It does not claim closure for source-library public replay, graph editing audit durability, typed knowledge UI persistence, writing workbench persistence, provider quality, or production semantic-vector conditions.

## Live Evidence

- Evidence JSON: [live_evidence.json](./live_evidence.json)
- Closure gate JSON: [closure_gate.json](./closure_gate.json)
- Backend base URL: `http://127.0.0.1:8000/api/v1`
- Tenant/project header: `X-Project-Key: demo_proj`
- Live DB/API smoke: `passed`
- Structured query endpoint: `passed`
- DocumentQuery statement builder execution against live `demo_proj` schema: `passed`
- Search/admin/dashboard/policy/prompt-time-density consumer read paths: `passed`

## Selected Readback

```text
GET /dashboard/stats
documents.total=218
sources.total=12
tasks.total=2531
```

```text
GET /search?q=embodied%20ai&rank=hybrid&top_k=3
results=3
document_query_results=3
search_backends_used=["opensearch_lexical"]
retrieval_run_readback.status=passed
```

```text
POST /admin/documents/list
total=218
ids=[777, 776, 775]
```

```text
DocumentQuery -> SQLAlchemy statement live execution
project_schema=demo_proj
row_count=3
ids=[777, 774, 773]
```

## Closure Gate

The Wave27 structured/consumer checker now accepts the manually collected live evidence:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_wave27_structured_consumer_closure.py \
  --live-evidence-json development/latest-dev-docs/automation-runs/wave45-manual-structured-consumer-live-api-closure/2026-05-23/live_evidence.json
```

Expected decision:

```text
decision.status=closed
external_blocker_count=0
validation.closure_ready=True
```
