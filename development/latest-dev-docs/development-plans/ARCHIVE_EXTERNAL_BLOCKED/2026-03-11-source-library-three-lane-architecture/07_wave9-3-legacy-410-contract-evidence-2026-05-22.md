# Wave9-3 Legacy 410 Contract Evidence (2026-05-22)

## Scope

This evidence closes the topic-local `doc_drift` around the old source-library item run endpoint. The three-lane architecture already routes execution through `POST /api/v1/ingest/source-library/run`; this lane adds the missing explicit contract for `POST /api/v1/source_library/items/{item_key}/run`.

No shared indexes were edited in this worker branch.

## Contract Landed

| Area | Status | Evidence |
| --- | --- | --- |
| Legacy endpoint behavior | Closed | `POST /api/v1/source_library/items/{item_key}/run` now returns `410 Gone` with standard error envelope and `meta.deprecated=source_library.legacy_item_run.v1`. |
| Replacement route pointer | Closed | The error details include `replacement_endpoint=/api/v1/ingest/source-library/run` and a minimal `replacement_payload` shape. |
| No accidental execution | Closed | The legacy endpoint returns before resolver/runner dispatch; checker asserts `runs_source_library_item=false`. |
| Deterministic gate | Closed | `main/backend/scripts/check_source_library_three_lane_legacy_run_contract.py` checks route table, response status/header/body/meta/details. |

## Validation Snapshot

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_library_three_lane_legacy_run_contract.py
```

Result: `status=pass`, `status_code=410`, `x_error_code=INVALID_INPUT`, `replacement_endpoint=/api/v1/ingest/source-library/run`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_three_lane_legacy_run_check_unittest.py \
  main/backend/tests/integration/test_project_key_policy_unittest.py \
  -k 'legacy_endpoint or legacy_run'
```

Result: `2 passed, 36 deselected`.

Broader source-library/route drift gate:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_three_lane_legacy_run_check_unittest.py \
  main/backend/tests/integration/test_project_key_policy_unittest.py \
  main/backend/tests/contract/test_api_route_drift_contract_unittest.py \
  main/backend/tests/unit/test_source_library_resolver_unittest.py \
  main/backend/tests/unit/test_source_library_runner_gray_rollout_unittest.py \
  main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py
```

Result: `76 passed`.

Core source-library API contract:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/core_business/test_source_library_core_contract.py
```

Result: `26 passed`.

Topic-local Markdown link gate:

```bash
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-11-source-library-three-lane-architecture
```

Result: `OK latest_dev_docs_structure=passed markdown_link_files=7 markdown_links=0`.

## Residual Risk

This lane does not re-run live source collection or alter the three-lane resolver/orchestrator taxonomy. It only closes the legacy route fallback evidence gap.
