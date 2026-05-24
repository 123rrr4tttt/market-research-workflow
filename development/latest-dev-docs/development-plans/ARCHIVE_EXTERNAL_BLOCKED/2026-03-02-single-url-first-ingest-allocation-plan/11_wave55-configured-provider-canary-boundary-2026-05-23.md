# Wave55 Configured-Provider Canary Boundary

Date: 2026-05-23

Scope: `2026-03-02-single-url-first-ingest-allocation-plan`

Worker: A2

## Result

`configured_provider_canary_boundary_landed`

This slice closes the repo-local boundary that was previously represented only by boolean live-canary evidence fields. A live single-URL canary can now be marked validated only when the evidence bundle includes:

- configured provider identity, runtime, config state, and live runtime status
- `ingest.url_pool` frontdoor execution with `source_mode=url_execution`
- public source URL readback from the single-URL/frontdoor run
- canary handoff readback with `ingest.single_url_canary_handoff.v1`

The default deterministic checker still keeps `demo_proj_live_canary_open=true`; it does not claim that public browser/runtime replay or a production 24h readback was run.

## Landed Surface

- `main/backend/app/services/ingest/canary_metrics.py`
- `main/backend/scripts/check_ingest_canary_metrics_readiness.py`
- `main/backend/tests/unit/test_ingest_canary_metrics_readiness_unittest.py`

## Remaining Boundary

Public browser/runtime replay across high-JS domains remains external/live evidence for this topic. Production 24h metrics readback and all-project strict-gate promotion also remain outside this repo-local slice.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_handoff_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_metrics_readiness.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_metrics_readiness_unittest.py main/backend/tests/unit/test_ingest_canary_handoff_unittest.py
```

Result: passed.
