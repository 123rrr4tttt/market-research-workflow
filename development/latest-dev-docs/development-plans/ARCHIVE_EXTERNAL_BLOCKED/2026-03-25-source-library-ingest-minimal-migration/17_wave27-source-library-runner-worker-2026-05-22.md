# Wave27 Source-Library Runner Worker (2026-05-22)

## Scope

This worker addresses the repo-local blocker
`python_library_cli_container_runners_not_enabled` for
`2026-03-25-source-library-ingest-minimal-migration`.

The change is intentionally bounded and deterministic. It does not run arbitrary
Python imports, arbitrary shell commands, or Docker containers. It enables the
source-library external-project runner surface for two predeclared runner
families:

- `python_library`
- `cli_or_container`

## Contract Landed

- Manifest/schema:
  - `external_item.manifest.v1` now accepts `execution_mode=python_library`.
  - `external_item.manifest.v1` now accepts `execution_mode=cli_or_container`.
  - `python-library://...`, `cli://...`, and `container://...` runner refs are
    treated as registered runner identities, not fetch URLs.
- Provider registry:
  - `external_project.python_library`
  - `external_project.cli_or_container`
- Runner:
  - Python-library execution is limited to the registered
    `source_library.fixture_records.v1` wrapper.
  - CLI/container execution is limited to the registered
    `source_library.fixture_json.v1` wrapper.
  - The CLI/container wrapper reports
    `predeclared_wrapper_no_arbitrary_shell`.
- Contract gate:
  - The AT-EXT checker now proves both runner families through deterministic
    fixture-backed runtime evidence.
  - `python_library_cli_container_runners_not_enabled` is no longer a remaining
    repo-local gap.

## Current Remaining Gaps

The topic is still not globally closed by this worker. Remaining gaps are live
or external-runtime evidence:

- `live_article_extraction_stack_replay_not_run`
- `live_external_project_replay_not_run`

## Validation

Commands run from `/Users/wangyiliang/market-research-workflow`:

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_external_project_registry_unittest.py \
  main/backend/tests/unit/test_source_library_external_project_adapter_unittest.py \
  main/backend/tests/unit/test_source_library_ingest_external_project_contract_check_unittest.py
```

Result: `13 passed, 2 warnings`.

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 \
  main/backend/scripts/check_source_library_ingest_external_project_contract.py
```

Result:

- `status`: `passed_with_known_gaps`
- `failures`: `[]`
- remaining gap codes:
  - `live_article_extraction_stack_replay_not_run`
  - `live_external_project_replay_not_run`

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_source_library_external_project_registration_unittest.py \
  main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py \
  main/backend/tests/core_business/test_source_library_core_contract.py \
  main/backend/tests/integration/test_external_project_collect_runtime_integration_unittest.py
```

Result: `42 passed, 11 warnings`.

## Closure Interpretation

This closes the repo-local runner enablement blocker at the deterministic
contract level. It does not claim live third-party replay, live article
extraction stack replay, or actual container startup.
