# Source Library Capability Service Map and Modular Rollout

Date: 2026-03-14

## 1. Decision

Continue the remediation under this architecture direction:

1. do not keep expanding `generic_web.search_template` as a monolithic adapter
2. extract reusable backend capability services
3. let adapters assemble those services based on capability profile
4. keep current external API and three-lane runtime behavior stable during the first phase

This is not a full routing rewrite in one step. Phase 1 should be a controlled extraction of capability modules under the existing runtime contract.

## 2. Problem Restatement

Current failures are not explained well by a lack of adapters alone. The bigger issue is that the existing search capability is split and duplicated across:

1. `source_library.adapters.generic_web`
2. `resource_pool.unified_search`
3. `handler.cluster` front-door execution

As a result:

1. the same `search_template` site can behave differently depending on entry path
2. capability logic is repeated instead of composed
3. adding rules to one path does not repair the others
4. error semantics collapse into generic empty/fetch failures

## 3. Current Service Map

### 3.1 Control Plane

These modules decide what path is used:

1. `source_library/item_resolver.py`
2. `source_library/resolver.py`
3. `source_library/orchestrators/*.py`

Current responsibility:

1. source mode resolution
2. lane selection
3. front-door vs URL execution routing
4. concurrency plan and fallback execution

### 3.2 Execution Plane

These modules actually perform source-specific work:

1. `source_library/adapters/generic_web.py`
2. `source_library/adapters/handler_cluster.py`
3. `resource_pool/unified_search.py`
4. `resource_pool/search_capabilities.py`
5. `resource_pool/auto_classify.py`
6. `ingest/source_search_contract.py`

Current reality:

1. `generic_web.py` already does URL normalization, pagination, fetch, link extraction, candidate scoring, fallback selection, and response packaging
2. `unified_search.py` duplicates a very similar `search_template/rss/sitemap` execution stack
3. `search_capabilities.py` is reusable, but only covers one slice of the pipeline

## 4. Target Architecture

### 4.1 Principle

Adapters should become assemblers, not monolithic executors.

The target shape is:

`item/channel capability profile -> adapter assembly plan -> capability services -> normalized candidate/result`

### 4.2 Capability Services to Extract

Phase-1 extraction should introduce the following backend services.

#### A. Search URL Builder

Responsibility:

1. normalize encoded placeholders
2. resolve `page/max_pages/page_size/sort/lang/region`
3. build one or many concrete search URLs from a template contract

Primary current logic sources:

1. `source_library/adapters/generic_web.py`
2. `resource_pool/unified_search.py`
3. `ingest/source_search_contract.py`

#### B. Page Fetch Service

Responsibility:

1. fetch HTML/XML/text with unified timeout and retry semantics
2. surface transport-classified errors
3. preserve response metadata for diagnostics

Primary current logic sources:

1. `ingest/adapters/http_utils.py`
2. `generic_web.py`
3. `unified_search.py`

#### C. Link Candidate Extractor

Responsibility:

1. extract links from search result HTML
2. extract item candidates from RSS/Atom
3. expand sitemap URLs into candidate URLs
4. normalize and de-duplicate candidate URLs

Primary current logic sources:

1. `generic_web.py`
2. `unified_search.py`

#### D. Candidate Selector

Responsibility:

1. score candidates against query terms
2. use title/text/title_hint/domain-aware heuristics
3. decide fallback behavior explicitly
4. emit normalized selection diagnostics

Primary current logic source:

1. `resource_pool/search_capabilities.py`

#### E. Capability Profile Resolver

Responsibility:

1. derive executable capability profile from `entry_type + channel_key + capabilities`
2. decide whether the source is `search`, `filter`, `static`, `api`, or unsupported
3. decide required services for that profile

Primary current logic sources:

1. `resource_pool/auto_classify.py`
2. `resource_pool/unified_search.py`

### 4.3 Adapter Assembly Contract

Adapters should assemble by profile, not by hardcoding end-to-end logic.

For content sites without official APIs, the authoritative runtime shape is:

`query -> site search -> candidate generation -> detail fetch`

Under this rule:

1. `search_template` is a primary search-stage capability
2. `rss` and `sitemap` are candidate-generation helpers, not authoritative detail-fetch paths
3. detail fetching happens only after candidate URLs are selected
4. the runtime should not treat site-entry feeds or sitemaps as equivalent to final fetch targets

Example target behavior:

1. `generic_web.search_template`
   - `SearchUrlBuilder`
   - `PageFetchService`
   - `HtmlLinkExtractor`
   - `CandidateSelector`

2. `generic_web.rss`
   - `PageFetchService`
   - `RssCandidateExtractor`
   - `CandidateSelector`

3. `generic_web.sitemap`
   - `PageFetchService`
   - `SitemapExpander`
   - `CandidateSelector`

4. `handler.cluster`
   - resolve `site_entries`
   - resolve capability profile per entry
   - assemble corresponding service chain
   - return normalized candidate batch

## 5. First-Phase Boundaries

Phase 1 must not attempt all of the following at once:

1. no full rewrite of `item_resolver` mode selection
2. no replacement of current three-lane runtime contract
3. no removal of `handler.cluster` or `unified_search`
4. no front-end or API contract change

Phase 1 should instead:

1. extract shared capability services from duplicated logic
2. make `generic_web` and `unified_search` consume the same services
3. keep current resolver/orchestrator branches intact
4. normalize diagnostics and errors across both call paths

## 6. Minimal File Plan

Recommended first-phase file set:

1. add `main/backend/app/services/resource_pool/source_capability_services.py`
2. keep `main/backend/app/services/resource_pool/search_capabilities.py` as the selector core
3. refactor `main/backend/app/services/source_library/adapters/generic_web.py` into a thin assembler
4. refactor `main/backend/app/services/resource_pool/unified_search.py` to use the same service helpers
5. add or extend unit tests for shared capability services

Optional follow-up file set after Phase 1 stabilizes:

1. `main/backend/app/services/source_library/item_resolver.py`
2. `main/backend/app/services/source_library/resolver.py`
3. `main/backend/app/services/source_library/adapters/handler_cluster.py`

## 7. Suggested Shared Types

Phase 1 should normalize these internal structures:

### 7.1 CapabilityProfile

Fields:

1. `entry_type`
2. `channel_key`
3. `keyword_mode`
4. `supports_query_terms`
5. `supports_pagination`
6. `fetch_format`
7. `extractor_kind`
8. `fallback_policy`

### 7.2 SearchFetchRequest

Fields:

1. `search_url`
2. `base_url`
3. `query_terms`
4. `timeout_seconds`
5. `page`
6. `page_size`
7. `extra`

### 7.3 CandidateBatch

Fields:

1. `candidates`
2. `used_fallback`
3. `pages_scanned`
4. `transport_errors`
5. `parse_errors`
6. `selection_diagnostics`

## 8. Rollout Order

### Stage 1

Extract pure helper services without changing resolver behavior.

Deliverables:

1. shared placeholder normalization
2. shared pagination resolution
3. shared search URL expansion
4. shared HTML/RSS/sitemap candidate extraction

### Stage 2

Switch `generic_web` to those shared services.

Acceptance:

1. `generic_web.search_template` behavior remains API-compatible
2. `generic_web.rss/sitemap` still work
3. direct internal adapter tests stay green

### Stage 3

Switch `unified_search` to the same shared services.

Acceptance:

1. `handler.cluster` path and direct `generic_web` path stop drifting
2. error taxonomy becomes comparable across paths

### Stage 4

Only after Stage 1-3 are stable, clean up control-plane routing and profile-based assembly.

This is where `item_resolver` and resolver branches should be reduced.

## 9. Risks and Mitigations

### Risk A: Hidden behavior drift

Cause:

1. `generic_web` and `unified_search` currently differ in subtle ways

Mitigation:

1. extract pure helpers first
2. port one call path at a time
3. compare before/after candidate outputs on the same sample sites

### Risk B: Over-coupling shared service to current search_template assumptions

Cause:

1. building the shared module around only current `search_template` behavior

Mitigation:

1. model service inputs by `CapabilityProfile`
2. keep extractor-specific logic separated inside the shared module

### Risk C: Regression in front-door contracts

Cause:

1. `handler.cluster` and resolver currently carry compatibility fields

Mitigation:

1. do not rewrite contract shaping in Phase 1
2. keep output shaping at the existing call boundary

## 10. Acceptance for This Architecture Direction

This direction is considered correctly adopted when:

1. `generic_web` no longer owns the full end-to-end search-template stack alone
2. `unified_search` and `generic_web` consume the same candidate-building services
3. `search_template/rss/sitemap` use one normalized extraction and selection model
4. real-site probe results become explainable by classified errors instead of generic empty failure buckets

## 11. Immediate Next Step

The next implementation round should start with:

1. create the shared capability service module
2. migrate `generic_web.search_template` to it
3. migrate `unified_search` search-template handling to it
4. run regression tests plus one real `demo_proj` site-entry probe

That is the smallest change that moves the codebase toward modular capability assembly without destabilizing the current three-lane runtime.
