# Lane 7 Landing: Mounting Fallback Assertions (2026-05-22)

## Scope

This note closes the smallest safe slice from the mounting audit: make the current source-library fallback order testable without adding new runtime entrypoints or changing agent-batch/process-retry metadata.

## Landed Assertion

The unconfigured URL routing fallback is now covered by a source-library unit assertion:

- search-like URLs with query terms resolve to `generic_web.search_template`
- sitemap URLs resolve to `generic_web.sitemap`
- ordinary article URLs fall back to `url_pool`

Test: `main/backend/tests/unit/test_source_library_resolver_unittest.py::SourceLibraryResolverUnitTestCase::test_url_router_prefers_keyword_aware_search_template_before_url_pool_default`

## Not Closed Here

The audit item “add consistent entrypoint markers to agent-batch/process-retry/ingest-sync logs and task metadata” is not closed in this lane. That change touches cross-entry orchestration metadata and should be handled by the agent-batch/process lane, not by this source-library capability worker.

## Validation Snapshot

Covered by the lane targeted pytest set: `160 passed, 3 warnings`.
