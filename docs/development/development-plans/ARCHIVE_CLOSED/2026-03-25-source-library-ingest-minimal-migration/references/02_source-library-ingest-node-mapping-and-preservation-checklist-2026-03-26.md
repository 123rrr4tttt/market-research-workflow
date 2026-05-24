# Source-Library / Ingest Node Mapping And Preservation Checklist

Updated: 2026-03-26 PST

## Purpose

This file is the execution-side preservation baseline for the current source-library / ingest migration topic.

It exists to prevent one class of failure:

- a node, call edge, output field, side effect, or observability hook disappears during migration because the new structure "conceptually covers it"

This checklist should be read together with:

- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](../01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [2026-03-25-source-library-to-db-service-flow-investigation.md](./2026-03-25-source-library-to-db-service-flow-investigation.md)
- [2026-03-25-ingest-structure-clarification-log.md](./2026-03-25-ingest-structure-clarification-log.md)
- [2026-03-26-source-library-ingest-expected-flow-v2.md](./2026-03-26-source-library-ingest-expected-flow-v2.md)

## Preservation Rule

For this topic, every migration step must satisfy all three conditions:

1. every current node must map to a retained node, a new owner layer, or an explicitly documented compatibility path
2. every current call chain must still be traceable through the new structure
3. no output, side effect, or observability signal may disappear without an explicit replacement note

If one item cannot be mapped, that migration step is not ready.

## Frozen Source Sets

The following source sets are frozen references during migration:

1. current code-shape investigation
- [2026-03-25-source-library-to-db-service-flow-investigation.md](./2026-03-25-source-library-to-db-service-flow-investigation.md)
- [2026-03-25-source-library-to-db-service-flow.drawio](./2026-03-25-source-library-to-db-service-flow.drawio)

2. structure clarification
- [2026-03-25-ingest-structure-clarification-log.md](./2026-03-25-ingest-structure-clarification-log.md)

3. corrected target views
- [2026-03-26-source-library-search-chain-expanded.md](./2026-03-26-source-library-search-chain-expanded.md)
- [2026-03-26-source-library-harvest-chain-expanded.md](./2026-03-26-source-library-harvest-chain-expanded.md)
- [2026-03-26-source-library-ingest-expected-flow-v2.md](./2026-03-26-source-library-ingest-expected-flow-v2.md)

## Node Mapping Matrix

### 1. Runtime Entry And Compile

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `loader.py` | explicit definition-sync node | cannot be hidden behind "definition sync" only | doc + code path |
| `sync.py` | explicit definition-sync node | same as above | doc + code path |
| `shared_ingest_channels` | explicit state node | do not replace with generic "shared state" wording only | doc |
| `shared_source_library_items` | explicit state node | same as above | doc |
| `POST /api/v1/ingest/source-library/run` | explicit runtime entry | cannot disappear from topic docs | doc |
| `_run_single_source_library_entry` | explicit API runtime node | may move layers, cannot be silently dropped | doc + code search |
| `task_run_source_library_item` | explicit async runtime node | async path must stay visible | doc + code search |
| `run_source_library_item_compat` | explicit compat runtime node | keep until compat removal is separately approved | doc + code search |
| `collect_request_from_source_library_api` | explicit adapter boundary | do not hide under "request build" | doc + code search |
| `run_collect` | explicit runtime node | keep collect-runtime boundary visible | doc + code search |
| `SourceLibraryAdapter.run` | explicit adapter node | cannot be replaced by generic "adapter" summary | doc + code search |
| `list_effective_channels` | explicit config node | keep effective config phase visible | doc |
| `list_effective_items` | explicit config node | keep effective config phase visible | doc |
| `run_item_payload` | explicit dispatch input node | do not merge into resolver summary | doc + code search |
| `ItemResolver.resolve` | explicit compile/dispatch node | keep as actual split point | doc + code search |

### 2. Runtime Views

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `protocol_search` | Search-chain runtime view | not a top-level standardized family | doc |
| `site_search` | Search-chain runtime view | not a top-level standardized family | doc |
| `url_execution` | Search-chain runtime view | not a top-level standardized family | doc |
| `provider_harvest` | Harvest-chain runtime view | remains Harvest-visible split point | doc |

### 3. Chain-specific Orchestrators

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `run_protocol_search_orchestrator` | explicit Search orchestrator | do not collapse into `run_channel` | doc + code search |
| `run_site_search_orchestrator` | explicit Search orchestrator | do not collapse into discovery branch summary | doc + code search |
| `run_url_execution_orchestrator` | explicit Search orchestrator | do not collapse into `run_item_with_url_routing` | doc + code search |
| `run_provider_harvest_orchestrator` | explicit Harvest orchestrator | do not collapse into provider dispatch summary | doc + code search |

### 4. Shared Called Services

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `run_single_channel_orchestrator` | shared orchestration service | first shared merge node | doc + code search |
| `run_channel` | shared orchestration service | keep separate from registry/dispatch | doc + code search |
| `handler_registry` | shared routing service | do not merge into `run_channel` wording only | doc + code search |
| route dispatch | shared routing function | keep Search-side dispatch visible | doc |
| provider dispatch | shared routing function | keep Harvest-side dispatch visible | doc |

### 5. Concrete Functions

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `google_news -> collect_google_news` | explicit compat function pair | do not reduce to `google_news` only | doc + code search |
| `reddit -> collect_reddit_discussions` | explicit compat function pair | same as above | doc + code search |
| `market -> collect_market_info` | explicit compat function pair | same as above | doc + code search |
| `policy -> ingest_policy_documents` | explicit direct function pair | keep separate from provider compat trio | doc + code search |
| `handler.cluster` | explicit discovery function | cannot be hidden behind "candidate discovery" | doc + code search |
| `unified_search_by_item_payload` | explicit discovery function | keep function-level name visible | doc + code search |
| `generic_web.rss` | explicit capability node | do not compress into `generic_web.*` only when preserving node list | doc |
| `generic_web.sitemap` | explicit capability node | same as above | doc |
| `generic_web.search_template` | explicit capability node | same as above | doc |
| `official_access.api` | explicit capability node | same as above | doc |

### 6. Shared Materialization Helpers

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `run_item_with_url_routing` | explicit shared materialization helper | keep as batch routing primitive | doc + code search |
| `collect_urls_from_list` | explicit shared materialization helper | keep until explicit compat-removal plan exists | doc + code search |
| `ingest_url_via_source_library_frontdoor` | explicit shared materialization helper | keep until explicit compat-removal plan exists | doc + code search |

### 7. Outputs And Side Effects

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `candidates` | explicit output node | cannot disappear under "intermediate results" | doc + tests |
| `by_url` | explicit output node | keep batch visibility | doc + tests |
| `records` | explicit output node | keep both Search and Harvest visibility | doc + tests |
| `stats` | explicit output node | keep field-level verification | tests |
| `legacy_counts` | explicit output node | keep until compat consumers are cleared | tests |
| `diagnostics` | explicit output node | keep until explicit replacement exists | tests |
| `rejection_breakdown` | explicit output node | keep batch aggregate semantics | tests |
| `degradation_flags` | explicit output node | keep batch aggregate semantics | tests |
| `append_url` | explicit side effect node | do not merge into generic "resource pool update" | doc + code search |
| `upsert_site_entry` | explicit side effect node | same as above | doc + code search |
| `resource_pool_urls` | explicit side effect target | keep target visibility | doc |
| `resource_pool_site_entries` | explicit side effect target | keep target visibility | doc |
| provider snapshots | explicit Harvest output concept | if renamed, add replacement note | doc + tests |
| compat counters | explicit Harvest output concept | if renamed, add replacement note | doc + tests |

### 8. Convergence And Frontdoor

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `SourceLibraryTerminalOutput v1` | explicit shared boundary | cannot be replaced by "terminal boundary" only | doc + tests |
| `build_source_library_ingress_envelope` | explicit convergence builder | keep until builder contract is versioned out | doc + tests |
| `build_frontdoor_ingress_envelope` | explicit convergence builder | same as above | doc + tests |
| `ingress_envelope` | explicit contract node | keep versioned contract visibility | tests |
| `document_candidate accept` | explicit ingress form | keep accept path wording | tests |
| `records-only defer` | explicit ingress form | keep defer path wording | tests |
| `run_postprocess_frontdoor` | explicit frontdoor node | do not collapse into "frontdoor" summary | doc + code search |
| `build_terminal_ingest_payload` | explicit payload-build node | keep if still present | doc + code search |
| `apply_terminal_compat` | explicit compat node | keep if still present | doc + code search |
| `persist_terminal_document` | explicit writer node | do not collapse into "writer" summary | doc + code search |
| `sources` | explicit write target | keep write target visibility | doc |
| `documents` | explicit write target | keep write target visibility | doc |

### 9. Observability

| Current Node | Must Be Preserved As | Migration Rule | Verification |
|---|---|---|---|
| `job_logger` | explicit logging node | cannot be hidden in generic observability box | doc + code search |
| `start_job / complete_job / fail_job` | explicit job lifecycle semantics | keep lifecycle visibility | tests |
| `etl_job_runs` | explicit table / sink node | keep sink visibility | doc + code search |
| `terminal_output` | explicit compat output | keep until consumers are cleared | tests |
| `legacy_result` | explicit compat output | keep until consumers are cleared | tests |
| trace | explicit signal | if renamed, add replacement note | tests |
| debug | explicit signal | if renamed, add replacement note | tests |
| metrics | explicit signal | if renamed, add replacement note | tests |
| contract drift monitoring | explicit gate | if postponed, mark as gap instead of deleting | doc |

## Execution Gates

### Gate 0. Before Any Structural Move

- every affected node has an entry in this file
- every removed box from the diagram can be expanded back to node-level entries here
- every compat helper has a stated owner and exit condition

### Gate 1. Before Changing Calls

- old caller is listed
- new caller is listed
- output fields are unchanged or have a replacement note
- side effects are unchanged or have a replacement note

### Gate 2. Before Deleting Any Compat Path

- all direct callers are enumerated
- all tests covering that path are listed
- replacement path is documented node by node
- rollback path still exists

### Gate 3. Before Declaring The Migration "Done"

- Search-side provider compat path is still traceable
- Search-side discovery path is still traceable
- Search-side url-execution path is still traceable
- Harvest-side direct path is still traceable
- Harvest-side compat path is still traceable
- shared convergence builders are still traceable
- frontdoor / writer / observability hooks are still traceable

## No-Silent-Loss Checklist

- Never replace a function pair like `google_news -> collect_google_news` with a provider name only.
- Never replace an output set like `by_url / records / diagnostics` with "batch result".
- Never replace `append_url / upsert_site_entry` with "resource-pool side effects".
- Never replace `run_postprocess_frontdoor` and `persist_terminal_document` with "frontdoor / writer" unless the node-level names remain elsewhere in the same document.
- Never delete `collect_urls_from_list`, `ingest_url_via_source_library_frontdoor`, `terminal_output`, `legacy_result`, or `job_logger` without a dedicated removal plan.

## Recommended Use During Execution

For every migration PR or change batch:

1. list touched nodes from this checklist
2. mark each as `unchanged`, `moved`, `wrapped`, or `replaced`
3. if `replaced`, add the exact replacement node name
4. if no exact replacement exists, stop and treat that as information loss
