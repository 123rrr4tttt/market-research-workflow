# Handler-Cluster Frontdoor Middle-Layer Alignment Closing (2026-03-06)

Date: 2026-03-06 (PST)
Status: closed
Owner: Codex + parallel agents

## Closure Summary

This plan is closed. The original goal was to align `handler-cluster/site-entry` execution onto the same system front-door middle layer used by URL routing and document ingestion, instead of letting resource-pool search own orchestration.

The final state is:

- `handler-cluster` no longer bypasses the front door from adapter-side special casing.
- candidate URLs re-enter front-door `url_routing` before ingest.
- `resource_pool/unified_search` remains a candidate-discovery capability, not the front-door owner.
- system middle-layer protocol fields now carry both search and routing execution context.
- project-level `crawler.*` is treated as runtime/config layer only.
- default front-door routing is now mechanical-first, with crawler kept as fallback.
- static URL-list items and runtime-provided URL lists now share the same front-door path.

## Verified Outcomes

- Source-library regression gate:
  - `tests/unit/test_source_library_resolver_unittest.py`
  - `tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`
  - result: `13 passed`
- Resource-pool regression gate:
  - `tests/unit/test_resource_pool_unified_search_unittest.py`
  - `tests/unit/test_resource_pool_search_capabilities_unittest.py`
  - result: `6 passed`
- Historical combined targeted gate for this workstream remains:
  - result: `19 passed`
- Static URL-list convergence check:
  - observed `execution_mode = url_routing`
  - observed static `url_pool.default` item and runtime URL list share the same routing path
- Live front-door replay:
  - item: `report1.root_site_search`
  - query-set: `["Humane AI Pin", "rabbit r1", "Oura Ring"]`
  - observed `single_write_workflow = front_door_url_routing`
  - observed default `prefer_crawler_first = false`
  - observed mechanical-first path uses `["url_pool", "generic_web.search_template"]`
  - observed `mechanical_first_30 = 20.092s`
  - observed `crawler_first_30 = 53.529s`
  - observed speedup: `2.664x`

## Final Architectural Decision

- System middle layer:
  - `search params + item/url -> front door -> routing -> ingest`
  - `url -> front door -> capability selection -> routing -> ingest`
- Non-goal:
  - no project-level `crawler.*` naming should be treated as an architecture layer
- Runtime default:
  - mechanical-first
  - crawler fallback on need or explicit override

## Closure Note

This workstream is complete enough to archive. Any further work should start as a new plan focused on:

- provider-internal concurrency tuning
- source quality weighting / ranking
- extraction pipeline noise reduction
