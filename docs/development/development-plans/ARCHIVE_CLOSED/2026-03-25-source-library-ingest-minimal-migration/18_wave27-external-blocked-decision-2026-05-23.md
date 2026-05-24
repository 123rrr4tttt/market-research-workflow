# Wave27 External-Blocked Decision: Source-Library Ingest Minimal Migration

> Date: 2026-05-23
> Status: external_blocked / wave27_checked

## Decision

Move `2026-03-25-source-library-ingest-minimal-migration` out of `CURRENT_DEV` and into `ARCHIVE_EXTERNAL_BLOCKED`.

The repo-local blocker named in Wave21, `python_library_cli_container_runners_not_enabled`, is now closed by the Wave27 bounded runner gate. The topic still is not full closure because live article-extraction stack replay and live external-project replay have not been run.

## Repo-Local Gate Closed

| Gate | Evidence |
|---|---|
| `python_library` runner family | `external_item.manifest.v1` accepts `execution_mode=python_library`, the provider registry exposes `external_project.python_library`, and the deterministic fixture runner `source_library.fixture_records.v1` executes through the external-project adapter. |
| `cli_or_container` runner family | `external_item.manifest.v1` accepts `execution_mode=cli_or_container`, the provider registry exposes `external_project.cli_or_container`, and the deterministic fixture runner `source_library.fixture_json.v1` executes without arbitrary shell/container startup. |
| AT-EXT current-state checker | `main/backend/scripts/check_source_library_ingest_external_project_contract.py` returns `status=passed_with_known_gaps` with `failures=[]`. |

## Remaining External Conditions

- `live_article_extraction_stack_replay_not_run`
- `live_external_project_replay_not_run`

These are live third-party/runtime replay conditions and should not keep this directory in `CURRENT_DEV` after the repo-local runner blocker is closed.

## Verification

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

Focused tests from the Wave27 runner worker:

- `13 passed, 2 warnings` for external-project registry / adapter / contract tests.
- `42 passed, 11 warnings` for adjacent registration, collect-runtime adapter, core contract, and integration coverage.
