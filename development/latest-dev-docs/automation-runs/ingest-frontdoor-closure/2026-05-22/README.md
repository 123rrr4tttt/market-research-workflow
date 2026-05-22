# Ingest / Frontdoor Closure Evidence (Wave3-H)

Date: 2026-05-22
Branch: `codex/devdocs-wave3-ingest-frontdoor-closure`
Scope: ingest/frontdoor closure lane

## Result

Status: `partial / current entry map aligned`.

This lane removes stale active-plan reliance on a non-existent `single_url.py` implementation target and pins the current write-capable URL ingest path:

```text
/api/v1/ingest/url/single
  -> main/backend/app/services/ingest/url_pool.py::ingest_url_via_source_library_frontdoor
  -> synthetic source-library item url_pool.single_url_compat
  -> source_library.resolver.run_item_with_url_routing(..., execution_layer="terminal_output_only")
  -> ingest.frontdoor_ingress
  -> ingest.postprocess_frontdoor
  -> ingest.terminal_writer
```

## Code Delta

- Fixed `collect_urls_from_pool` sync/thread frontdoor execution so `_run_single_target` receives the current pool target instead of reading the loop variable captured from the previous runtime-target build.
- Added focused regression coverage for two pool search-template targets with different `source_search_contract` values. The test asserts that each target's `param_key`, `target_candidates`, and frontdoor `route_hint` survive routing independently.

## Docs Delta

- `2026-03-02-single-url-first-ingest-allocation-plan` now treats `single_url` as a legacy contract name, not an active file path.
- `2026-03-02-ingest-platformization-assessment` now maps the single write workflow to the source-library/frontdoor chain.
- `2026-03-08-llm-crawler-unified-frontdoor` records the Wave3-H target-context regression and keeps broader router/tri-state gaps open.
- `CURRENT_DEV/INDEX.md`, `README.md`, and `MERGED_OVERVIEW.md` link this evidence package.

## Remaining Risks

- High-JS/browser-render/crawler-first routing is still broader fetch-router work.
- Official API routing still depends on source-library adapter maturity.
- Frontend/dashboard tri-state display can still differ from inner frontdoor admission state and remains out of this lane.

## Validation

Focused ingest/frontdoor pytest:

```bash
cd main/backend
python3.11 -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py tests/unit/test_frontdoor_orchestrator_unittest.py tests/unit/test_postprocess_frontdoor_unittest.py tests/core_business/test_ingest_core_contract.py tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py
```

Result: `45 passed, 11 warnings`.

Changed Markdown link check:

```bash
python3 - <<'PY'
...
PY
```

Result: `PASSED changed markdown link check: files=8 links=332`.

Whitespace/checkpatch gate:

```bash
git diff --check
```

Result: passed.
