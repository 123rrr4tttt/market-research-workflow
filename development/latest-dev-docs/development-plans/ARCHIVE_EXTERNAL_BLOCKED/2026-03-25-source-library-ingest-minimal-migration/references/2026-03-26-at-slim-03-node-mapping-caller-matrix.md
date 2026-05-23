# AT-SLIM-03 Node Mapping And Caller Matrix

Updated: 2026-03-26 PST

## Purpose

This file is the execution-side output for `AT-SLIM-03`.

It freezes the touched nodes and caller relationships that must remain
traceable for the current source-library / ingest minimal migration
topic.

This sheet should be read together with:

- [../01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [../02_wave0-freeze-and-acceptance-contract-2026-03-26.md](../02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
- [../03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](../03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
- [2026-03-25-source-library-to-db-service-flow-investigation.md](./2026-03-25-source-library-to-db-service-flow-investigation.md)
- [02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md](./02_source-library-ingest-node-mapping-and-preservation-checklist-2026-03-26.md)

## Scope

The matrix covers the nodes that are explicitly frozen in the current
topic plan and that are relevant to the next execution waves:

- runtime entry and compat entry nodes
- source-library execution and routing nodes
- ingest frontdoor convergence nodes
- compat / observability boundary nodes
- current upstream callers that enter the batch path

## Node Mapping Matrix

### 1. Runtime Entry And Compat Entry

| Current Node | Current Owner / Layer | Current Callers | New Owner / Layer | Replacement Note | Rollback Path |
|---|---|---|---|---|---|
| `POST /api/v1/ingest/source-library/run` | API runtime entry | HTTP clients, test harnesses | keep as API runtime entry | no replacement; keep explicit runtime boundary | same endpoint, same payload shape |
| `_run_single_source_library_entry` | API orchestration helper | `ingest_source_library_run(...)` | keep as API orchestration helper | no replacement; may stay as thin runtime helper | same helper; async/sync split remains visible |
| `task_run_source_library_item` | Celery task boundary | `_dispatch_source_library_item_async(...)` | keep as async runtime boundary | no replacement; async path remains traceable | same Celery task |
| `run_source_library_item_compat` | collect-runtime compat boundary | `ingest/api`, `task_run_source_library_item` | keep as compat boundary | no replacement; caller must still see compat wrapper | direct compat call remains available |
| `collect_request_from_source_library_api` | collect-runtime request builder | `run_source_library_item_compat` | keep as request builder | no replacement; request construction stays explicit | same builder function |
| `run_collect` | collect-runtime dispatch entry | `collect_request_from_source_library_api`, other collect adapters | keep as runtime entry | no replacement; retain adapter boundary visibility | legacy collect path remains default |
| `SourceLibraryAdapter.run` | collect adapter | `run_collect` | keep as collect adapter | no replacement; adapter remains explicit | same adapter implementation |
| `list_effective_channels` | source-library config resolution | `SourceLibraryAdapter.run`, `ingest/url_pool.py` | keep as config resolution node | no replacement; preserve effective config phase | same lookup path |
| `list_effective_items` | source-library config resolution | `SourceLibraryAdapter.run` | keep as config resolution node | no replacement; preserve effective config phase | same lookup path |
| `run_item_payload` | source-library dispatch input | `SourceLibraryAdapter.run` | keep as dispatch input node | no replacement; do not collapse into resolver summary | same dispatch input path |
| `ItemResolver.resolve` | source-library compile/dispatch split | `run_item_payload` | keep as compile/dispatch split point | no replacement; remains visible as decision boundary | same resolver path |

### 2. Runtime Views And Orchestrators

| Current Node | Current Owner / Layer | Current Callers | New Owner / Layer | Replacement Note | Rollback Path |
|---|---|---|---|---|---|
| `protocol_search` | runtime view | `ItemResolver.resolve` | keep as Search runtime view | no replacement; runtime projection stays explicit | same runtime projection |
| `site_search` | runtime view | `ItemResolver.resolve` | keep as Search runtime view | no replacement | same runtime projection |
| `url_execution` | runtime view | `ItemResolver.resolve` | keep as Search runtime view | no replacement | same runtime projection |
| `provider_harvest` | runtime view | `ItemResolver.resolve` | keep as Harvest runtime view | no replacement | same runtime projection |
| `run_protocol_search_orchestrator` | Search orchestrator | runtime views | keep as Search orchestrator | no replacement; do not collapse into shared service wording | same orchestrator |
| `run_site_search_orchestrator` | Search orchestrator | runtime views | keep as Search orchestrator | no replacement | same orchestrator |
| `run_url_execution_orchestrator` | Search orchestrator | runtime views | keep as Search orchestrator | no replacement | same orchestrator |
| `run_provider_harvest_orchestrator` | Harvest orchestrator | runtime views | keep as Harvest orchestrator | no replacement | same orchestrator |
| `run_single_channel_orchestrator` | shared orchestration service | Search / Harvest orchestrators | keep as shared orchestration service | no replacement; first shared merge node remains visible | same service entry |
| `run_channel` | shared routing service | `run_single_channel_orchestrator` | keep as shared routing service | no replacement; separate from registry/dispatch wording | same service entry |
| `handler_registry` | routing registry | `run_channel` | keep as registry node | no replacement | same registry |
| route dispatch | shared routing step | `run_channel` | keep as shared routing step | no replacement; should remain explicit | same route dispatch |
| provider dispatch | shared routing step | `run_channel` | keep as shared routing step | no replacement | same provider dispatch |

### 3. Concrete Execution Nodes And Side-Effect Nodes

| Current Node | Current Owner / Layer | Current Callers | New Owner / Layer | Replacement Note | Rollback Path |
|---|---|---|---|---|---|
| `handler.cluster` | search discovery function | `run_channel` | keep as discovery function | no replacement; must remain explicit | same discovery function |
| `unified_search_by_item_payload` | search discovery function | `handler.cluster` | keep as discovery function | no replacement | same discovery function |
| `run_item_with_url_routing` | shared materialization helper | `collect_urls_from_list`, `ingest_url_via_source_library_frontdoor` | keep as shared materialization helper | no replacement; batch routing primitive in Wave 2 | same helper, same outputs |
| `collect_urls_from_list` | batch runtime entry | `ingest/news.py`, `ingest/market_web.py`, `resource_pool/unified_search.py`, other URL providers | keep as batch runtime entry | no replacement; target owner for Wave 3 switch work | same function, legacy path preserved |
| `ingest_url_via_source_library_frontdoor` | single-URL compatibility path | `collect_urls_from_list`, direct API / runtime callers | keep as compatibility path | no replacement; remains single-URL path | same function, same contract |
| `build_source_library_ingress_envelope` | convergence builder | `collect_runtime/adapters/source_library.py`, `frontdoor` callers | keep as shared convergence builder | no replacement; explicit pre-frontdoor boundary stays visible | same builder |
| `build_frontdoor_ingress_envelope` | convergence builder | `ingest/url_pool.py`, direct frontdoor callers | keep as shared convergence builder | no replacement | same builder |
| `run_postprocess_frontdoor` | frontdoor admission/output engine | `ingest/url_pool.py`, `ingest/news.py`, `ingest/market_web.py`, `frontdoor` callers | keep as frontdoor engine | no replacement; do not compress into generic frontdoor summary | same function |
| `persist_terminal_document` | writer boundary | `run_postprocess_frontdoor` | keep as writer boundary | no replacement; explicit writer node stays visible | same writer path |
| `terminal_output` | compat output | `collect_runtime/adapters/source_library.py`, downstream consumers | keep as compat output | no replacement; keep until a dedicated removal plan exists | same output field |
| `legacy_result` | compat output | `collect_runtime/adapters/source_library.py` | keep as compat output | no replacement | same output field |
| `job_logger` | observability boundary | runtime entry, adapters, frontdoor flow | keep as observability boundary | no replacement; keep lifecycle hooks visible | same logging boundary |
| `etl_job_runs` | job sink / table | `job_logger` | keep as sink visibility node | no replacement | same sink |

### 4. Shared Caller Matrix For Current Batch Path

| Current Caller | Current Callee | Current Role | New Owner / Layer | Replacement Note | Rollback Path |
|---|---|---|---|---|---|
| `ingest/news.py::_dispatch_links_via_source_library_frontdoor(...)` | `collect_urls_from_list(...)` | URL-provider batch ingest | keep as provider caller of batch runtime entry | no replacement; this is a current batch caller that should remain traceable | `collect_urls_from_list(...)` legacy path remains |
| `ingest/market_web.py` routed body fetch path | `collect_urls_from_list(...)` | body-fetch batch ingest | keep as provider caller of batch runtime entry | no replacement | legacy per-URL path remains inside `collect_urls_from_list(...)` |
| `resource_pool/unified_search.py` auto-ingest path | `collect_urls_from_list(...)` | current-run candidate ingest | keep as search-side caller of batch runtime entry | no replacement | same function with `url_target_mode=detail_only` fallback |
| `collect_runtime/adapters/url_pool.py` | `collect_urls_from_list(...)` | runtime adapter entry | keep as adapter caller of batch runtime entry | no replacement | same adapter, same payload shape |
| `collect_runtime/adapters/source_library.py` | `build_source_library_ingress_envelope(...)`, `run_postprocess_frontdoor(...)` | compat / write-through boundary | keep as compat caller and boundary adapter | no replacement | same compat adapter path |
| `api/ingest.py::_run_single_source_library_entry(...)` | `run_source_library_item_compat(...)` | source-library runtime entry | keep as API caller of compat entry | no replacement | same compat entry |
| `tasks.py::task_run_source_library_item(...)` | `run_source_library_item_compat(...)` | async source-library task | keep as async caller of compat entry | no replacement | same Celery task |

### 5. Side-Effect And Output Mapping

| Current Node | Current Owner / Layer | Current Callers | New Owner / Layer | Replacement Note | Rollback Path |
|---|---|---|---|---|---|
| `candidates` | search discovery output | `handler.cluster`, downstream search consumers | keep as discovery output | no replacement | same field |
| `records` | routed output / frontdoor input | `run_item_with_url_routing`, `collect_urls_from_list` | keep as middle-output node | no replacement | same field |
| `by_url` | routed output | `run_item_with_url_routing`, `collect_urls_from_list` | keep as middle-output node | no replacement; must remain visible in batch output | same field |
| `stats` | routed output | `run_item_with_url_routing`, `collect_urls_from_list` | keep as middle-output node | no replacement | same field |
| `rejection_breakdown` | batch output | `collect_urls_from_list`, routings | keep as batch output | no replacement; do not collapse into generic failure count | same field |
| `diagnostics` | routed/batch output | `run_item_with_url_routing`, `collect_urls_from_list` | keep as diagnostics output | no replacement | same field |
| `degradation_flags` | batch output | `collect_urls_from_list`, frontdoor responses | keep as batch output | no replacement | same field |
| `append_url` | resource-pool write side effect | discovery / search template flows | keep as explicit side effect | no replacement | same write path |
| `upsert_site_entry` | resource-pool write side effect | discovery / search template flows | keep as explicit side effect | no replacement | same write path |
| `resource_pool_urls` | pool state | `append_url` | keep as pool state target | no replacement | same table / store |
| `resource_pool_site_entries` | pool state | `upsert_site_entry` | keep as pool state target | no replacement | same table / store |

## Current Caller / Callee Notes

- `collect_urls_from_list(...)` is the active batch runtime entry for URL
  provider callers and search-side auto-ingest callers.
- `ingest_url_via_source_library_frontdoor(...)` is the current single-URL
  compatibility path and stays the rollback anchor for later batch changes.
- `run_item_with_url_routing(...)` is still called by the single-URL
  compatibility path today and is the future batch-routing helper boundary.
- `build_source_library_ingress_envelope(...)` is the source-library
  compatibility bridge into frontdoor; `build_frontdoor_ingress_envelope(...)`
  is the generic frontdoor contract builder.
- `run_postprocess_frontdoor(...)` remains the admission / normalization /
  writer gate and should stay separately traceable from the builder.

## Execution Gate

Before Wave 2 or later structural edits, any touched node here must be
kept in sync with the plan and reference pack.

If a later change cannot preserve one of these names or a precise
replacement node name, the change is not ready.

## Recommended Validation

- `rg -n "run_item_with_url_routing|collect_urls_from_list|ingest_url_via_source_library_frontdoor|build_source_library_ingress_envelope|build_frontdoor_ingress_envelope|run_postprocess_frontdoor|job_logger|etl_job_runs|terminal_output|legacy_result" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration/references/2026-03-26-at-slim-03-node-mapping-caller-matrix.md -S`
