# Wave10 Source-Library Search Governance - Mounting Audit Slice (2026-05-22)

## Scope

This Wave10 slice lands a no-network governance checker for the search-chain/source-library mounting boundary.

Checker:

- `main/backend/scripts/check_source_library_search_governance.py`

Evidence:

- `development/latest-dev-docs/automation-runs/source-library-search-governance/2026-05-22/output.json`

## Mounting Assertions Now Checked

| Boundary | Checked state |
| --- | --- |
| Authoritative source-library run front door | `POST /api/v1/ingest/source-library/run` remains active. |
| Legacy item run endpoint | `POST /api/v1/source_library/items/{item_key}/run` remains `410_gone_no_execution`. |
| Agent-batch async entry | `POST /api/v1/agent-batch/jobs` still submits source-library work through `_submit_source_library_job -> _submit_source_item`. |
| Process retry bypass | `POST /api/v1/process/{task_id}/retry` is recorded as an active bypass that dispatches `agent_batch.dispatch.source_library_item`. |
| Resource-pool unified search | `/api/v1/resource_pool/unified-search` remains a capability endpoint, not the authoritative source-library front door. |

## Resolver Assertions Now Checked

- `handler.cluster` source items resolve to `site_search`.
- An explicit `source_mode=protocol_search` is coerced back to `site_search` for site-search authoritative taxonomy.
- Runtime candidate URLs override to `url_execution`.
- `generic_web.*` remains an internal adapter surface and emits the internal-adapter warning.
- `site_search` orchestration forces execution through `handler.cluster`.

## Not Claimed Closed

This lane does not add the missing cross-entry `entrypoint` metadata markers for agent-batch/process-retry/ingest-sync logs. It records the process retry route as a known bypass requiring metadata governance, matching the existing mounting audit boundary.

## Validation

```bash
python3.11 main/backend/scripts/check_source_library_search_governance.py --repo-root .
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_search_governance_check_unittest.py
```

Result: checker passed; unit test `2 passed, 2 warnings`.
