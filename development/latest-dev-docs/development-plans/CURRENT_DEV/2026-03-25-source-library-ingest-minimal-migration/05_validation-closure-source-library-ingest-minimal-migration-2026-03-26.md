# Validation Closure: Source-Library / Ingest Minimal Migration (2026-03-26)

## 1. Scope

This closure covers the full `AT-SLIM-01` to `AT-SLIM-10` migration round for:

- source-library batch routing helper extraction
- batch-path switch and rollback contract
- shared ingress builder convergence
- documentation and navigation closure

## 2. Closure Result

The migration is closed with the following preserved boundaries:

- `run_item_with_url_routing(...)` freezes `runtime_targets` before materialization
- `collect_urls_from_list(...)` owns raw normalization, target expansion, de-duplication, and batch-path selection
- `url_batch_path_mode` is the explicit selector for batch-path rollback
- `settings.url_batch_path_default_mode` is the repo-level default knob
- `build_source_library_ingress_envelope(...)` and `run_postprocess_frontdoor(...)` are the shared ingress path for collect-runtime compatibility
- the current expected runtime shape also allows source-library
  materialization to hand off a downloaded PDF artifact at pre-frontdoor
  time through `record_meta.artifact_ref` and
  `collection_payload.source_artifacts`; downstream PDF-specific parsing
  remains a later task

## 3. Regression Pack

Validation was re-run against the minimum closure pack required by `AT-SLIM-10`:

```bash
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_source_library_resolver_unittest.py
python3.11 -m pytest -q main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py
python3.11 -m pytest -q main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/core_business/test_source_library_core_contract.py
```

Results:

- `23 passed` for `test_source_library_item_resolver_unittest.py` + `test_source_library_resolver_unittest.py`
- `10 passed, 3 warnings` for `test_source_library_terminal_output_unittest.py` + `test_collect_runtime_source_library_adapter_unittest.py`
- `18 passed, 12 warnings` for `test_postprocess_frontdoor_unittest.py` + `test_source_library_core_contract.py`

## 4. Call-Chain Matrix

Search-side provider compat path remains traceable through the source-library resolver and its adapter-facing callers.

Search-side discovery and url-execution paths remain traceable through:

- `collect_urls_from_list(...)`
- `collect_runtime/adapters/url_pool.py`
- `run_item_with_url_routing(...)`

Harvest-side direct and compat paths remain traceable through:

- `collect_runtime/adapters/source_library.py`
- `build_source_library_ingress_envelope(...)`
- `run_postprocess_frontdoor(...)`

Frontdoor, writer, and observability hooks remain traceable through:

- `frontdoor_ingress.py`
- `postprocess_frontdoor.py`
- metrics / job logger integration points in the ingest path

## 5. Compat Retention Status

The following compatibility surfaces are still intentionally retained:

- `legacy_result`
- `terminal_output`
- `frontdoor_ingress`
- `postprocess_frontdoor`
- `collect_urls_from_list(...)` legacy override path
- async dispatch fallback to legacy per-URL routing

These are preserved by design and remain covered by regression tests.

## 6. Residual Risks

The remaining risk is maintenance, not correctness:

- `url_pool.py` remains a dense compatibility boundary while the migration still carries both routing paths
- the repo-level batch default now favors `batch_runtime_targets`, so any future rollback should continue to use the explicit knob and not frontdoor rollout settings
- a separate async-batch plan would be needed before async dispatch could safely adopt the batch helper

No blocking correctness issue remains for this migration round.

## 7. Post-Closure Runtime Expectation Addendum

To keep the current-dev expectation aligned with the latest runtime
behavior:

- when a source-library URL materialization step resolves a primary PDF
  source, the frontdoor-facing payload is expected to carry the PDF
  itself as a local artifact, not only a PDF URL
- the retained handoff fields are expected to include `local_path`,
  `sha256`, `byte_size`, `mime_type`, and `source_locator`
- downstream PDF extraction / normalization is explicitly out of scope
  for this migration closure and should be handled by a later adapter
  task
