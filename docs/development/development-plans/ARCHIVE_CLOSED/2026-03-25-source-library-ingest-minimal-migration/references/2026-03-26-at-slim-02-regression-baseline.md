# AT-SLIM-02 Regression Baseline

Updated: 2026-03-26 PST

## Purpose

This file freezes the current regression surface for `AT-SLIM-02` before
any structural code move in the source-library / ingest minimal migration.

It is the task-local evidence artifact for the current freeze wave.

## Frozen Contract Surface

The baseline covers the following current contracts:

- `run_item_with_url_routing(...)`
- `collect_urls_from_list(...)`
- `ingest_url_via_source_library_frontdoor(...)`
- `run_postprocess_frontdoor(...)`
- `SourceLibraryTerminalOutput v1`

The freeze was taken after confirming the Wave 0 contract baseline and
the current implementation reality documented in:

- [../01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [../02_wave0-freeze-and-acceptance-contract-2026-03-26.md](../02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
- [2026-03-25-source-library-to-db-service-flow-investigation.md](./2026-03-25-source-library-to-db-service-flow-investigation.md)

## Regression Pack

### Resolver Layer

- `main/backend/tests/unit/test_source_library_resolver_unittest.py`
- `main/backend/tests/unit/test_source_library_item_resolver_unittest.py`

### Terminal Output And Frontdoor Layer

- `main/backend/tests/unit/test_source_library_terminal_output_unittest.py`
- `main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`

## Validation Result

All regression tests in the freeze pack passed on 2026-03-26 PST.

### Resolver Layer

- `22 passed`

### Terminal Output And Frontdoor Layer

- `13 passed`

### Combined Result

- `35 passed`
- `0 failed`
- `0 skipped`

## Notes

- No code changes were required for this baseline freeze.
- The current contract surface is already backed by green tests.
- The only warnings observed during validation were pre-existing
  dependency deprecation warnings from `langchain` and `pydantic`.

## Recommended Re-Run

If the freeze needs to be refreshed later, rerun:

```bash
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_source_library_item_resolver_unittest.py
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py
```
