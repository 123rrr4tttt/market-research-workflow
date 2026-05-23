# Ingest Chain Full Branch Map Closure Evidence (2026-05-23)

Status: `closed / wave39_verified`

## Scope

This closes the evidence gap for
`01_ingest-chain-full-branch-map-2026-03-02.md`.

The closed requirement is not a live provider replay. It is the repo-local
branch-map contract for the ingest chain:

- ingest API errors use standard envelopes and headers;
- frontend ingest flow can queue source-library and single-url work;
- source-library handler-cluster frontdoor routes through bounded unified
  search batches and preserves the candidate pipeline contract.

## Evidence

Code and tests bound to this target:

- `main/backend/tests/core_business/test_ingest_core_contract.py`
- `main/backend/tests/integration/test_frontend_ingest_flow_smoke_unittest.py`
- `main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
- `main/backend/app/api/ingest.py`
- `main/backend/app/services/collect_runtime/adapters/source_library.py`
- `main/backend/app/services/resource_pool/unified_search.py`
- `main/backend/app/services/ingest/single_url.py`

## Validation

Run from the repository root:

```bash
cd main/backend
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  tests/core_business/test_ingest_core_contract.py \
  tests/integration/test_frontend_ingest_flow_smoke_unittest.py \
  tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py
```

Observed: `29 passed`.

## Remaining Boundary

Live public-provider replay, anti-bot behavior, and production project-schema
visibility remain separate external checks. They are not required to close this
repo-local branch-map target.
