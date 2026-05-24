# Wave55 Production-like Canary Handoff

Date: 2026-05-24
Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

## status

`repo_local_production_like_canary_handoff_landed`

## what changed

This slice adds a repo-local production-like canary handoff instead of keeping the
Wave12 handoff at deterministic envelope visibility only.

The new runtime path executes the ingest URL API against a temporary local
Postgres project schema, patches only external fetch and LLM extraction with
deterministic fixtures, and leaves the normal API, frontdoor guardrails,
`terminal_writer`, DB write, and DB readback path live.

Contract markers:

- `repo_local_api_db_runtime`
- `live_canary_validated=true`
- `closure_claim=false`
- `remaining_external_gaps`

## evidence

- `main/backend/app/services/ingest/canary_handoff.py`
- `main/backend/app/services/ingest/canary_handoff_live.py`
- `main/backend/scripts/check_ingest_canary_handoff_contract.py`
- `main/backend/tests/unit/test_ingest_canary_handoff_live_unittest.py`

## canary behavior

The production-like runner performs two API calls through
`POST /api/v1/ingest/url/single`:

- accepted article URL: strict canary gate passes, `terminal_writer` inserts one
  document, and DB readback finds exactly one accepted document.
- rejected `/search` URL: strict canary gate blocks the low-value endpoint, no
  document is inserted, and DB readback finds zero rejected documents.

The validated handoff now reports `handoff_state=live_canary_validated` for the
repo-local API/DB canary evidence. It deliberately keeps `closure_claim=false`
because production 24h rejection-rate readback, production 24h inserted-valid
ratio readback, and operations-owned all-project strict-gate promotion remain
outside this repo-local worker.

## validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_ingest_canary_handoff_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_ingest_canary_handoff_live_unittest.py main/backend/tests/unit/test_ingest_canary_handoff_unittest.py
git diff --check
```
