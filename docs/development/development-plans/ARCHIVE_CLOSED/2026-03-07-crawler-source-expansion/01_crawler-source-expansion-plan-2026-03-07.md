# Crawler Source Expansion Plan (2026-03-07)

> Date: 2026-03-07
> Scope: crawler onboarding, directed source expansion, source-layer governance, ingest handoff
> Status: planning document for freezing problem framing, boundaries, and phase-1 execution order

## 1. Objective

This topic is not "add more adapters" in isolation.
It exists to turn the current source-related capabilities into a more explicit source system with:

1. a stable source tiering model;
2. a clear onboarding boundary for new crawlers and source adapters;
3. a minimum quality and dedupe policy at source-layer time;
4. a predictable handoff into downstream ingest.

The immediate deliverable is a plan that can guide the next implementation round without pretending phase-1 already knows every future provider or source list.

## 2. Current Baseline

### 2.1 Existing repo entry points

The repo already has a non-trivial source stack.
Confirmed entry points include:

- Frontend management page:
  - `main/frontend-modern/src/pages/CrawlerManagePage.tsx`
- Backend APIs:
  - `main/backend/app/api/crawler.py`
  - `main/backend/app/api/source_library.py`
- Source-library services:
  - `main/backend/app/services/source_library/*`
- Crawler runtime and provider services:
  - `main/backend/app/services/crawlers/*`
  - `main/backend/app/services/crawlers/providers/*`
  - `main/backend/app/services/crawlers_mgmt/*`
- Collection and discovery chains:
  - `main/backend/app/services/collect_runtime/*`
  - `main/backend/app/services/discovery/*`

This means the source layer is already operational in pieces.
The missing part is a stronger system-level framing across these pieces.

### 2.2 Reusable contracts already in repo

The current backend already exposes reusable contract anchors:

- `source_library/types.py`
  - `ChannelRecord`
  - `SourceItemRecord`
  - `FrontDoorExecutionProtocol`
- `collect_runtime/contracts.py`
  - `CollectRequest`
  - `CollectResult`
- `crawlers/base.py`
  - `CrawlerDispatchRequest`
  - `CrawlerDispatchResult`

These files indicate that the repo already has:

- a source definition layer;
- a normalized collection request/result layer;
- a provider-specific crawler dispatch layer.

That is enough to define a better layered plan without inventing an entirely new architecture.

### 2.3 Existing source coverage hints

The repo already includes several concrete source-library adapters, such as:

- `google_news`
- `reddit`
- `official_access`
- `generic_web`
- `market`
- `url_pool`
- `handler_cluster`

It also already includes collect-runtime adapters such as:

- `source_library`
- `url_pool`
- `search_market`
- `crawler_scrapy`

This suggests the immediate gap is not "zero source support".
The real gap is the absence of a documented and enforced rule for when a source belongs in:

- source cataloging,
- normalized collection,
- provider dispatch,
- discovery augmentation.

### 2.4 Existing quality anchors

Quality-related logic is already present in multiple places:

- `main/backend/app/services/ingest/meaningful_gate.py`
- `main/backend/app/services/resource_pool/llm_validator.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/discovery/store.py`

The problem is not the total absence of quality checks.
The problem is that source quality, dedupe, and stability are still mostly implicit or downstream-heavy.

### 2.5 Baseline gaps

The current baseline still lacks a clearly documented answer to the following:

- Which source classes are baseline platform sources versus directed high-value sources versus experimental sources.
- What the exact responsibility split is between `source_library`, `collect_runtime`, `crawlers/providers`, and `discovery`.
- Which quality checks must happen before ingest rather than after ingest.
- How directed sources such as academic, business intelligence, reports, and news should be prioritized.
- What the minimum source-to-ingest handoff object should contain.

## 3. Requirement Clarification

### 3.1 Main scenarios

This plan is for the moment when the team needs to do one of the following safely:

- add a new directed source family;
- introduce a new crawler provider or crawler strategy;
- decide whether an LLM-assisted crawler is a provider, a runtime strategy, or an enrichment step;
- keep downstream ingest and knowledge organization from being polluted by unstable source metadata.

### 3.2 What phase-1 must answer

Phase-1 must answer these questions explicitly:

1. How many source tiers are needed, and what belongs in each tier?
2. What is the onboarding path for a new source or crawler capability?
3. Which minimum quality checks are source-layer responsibilities?
4. Which directed source families should be prioritized first, and why?
5. What minimum normalized output should downstream ingest receive?

### 3.3 What phase-1 does not need to answer yet

Phase-1 does not need to:

- produce a complete external source list;
- select every future crawler framework up front;
- redesign the downstream ingest system;
- commit to a final scoring model for all source quality dimensions.

## 4. Scope and Non-Goals

### 4.1 In scope

This document currently covers:

- source type tiering and priority;
- onboarding boundary for crawler/source-related capabilities;
- quality, dedupe, and stability governance at source-layer time;
- directed source strategy for academic, business-report, business-information, and news classes;
- minimum handoff semantics from source layer to ingest.

### 4.2 Out of scope

This document does not attempt to finalize:

- the full ingest digestion design;
- the full typed knowledge organization design;
- global LLM platform architecture;
- one-shot mass onboarding of all candidate sources;
- final UI/ops workflows for source management.

## 5. Recommended Layering and Plan Shape

### 5.1 Recommended source tiers

The source portfolio should be described with at least three tiers:

- Tier 1: baseline platform sources
  - General-purpose, repeatable, broad-coverage sources that fit stable ongoing operation.
- Tier 2: directed high-value sources
  - Academic, business report, business-information, or domain-targeted sources that justify extra onboarding and governance effort.
- Tier 3: experimental or augmentation sources
  - LLM-assisted crawlers, exploratory discovery paths, or unstable sources that should not silently become the default backbone.

The main point of the tier model is prioritization and governance, not taxonomy for taxonomy's sake.

### 5.2 Recommended runtime responsibility split

Based on current repo structure, the recommended boundary is:

- `source_library/*`
  - Owns source/channel/item definitions, routing metadata, and reusable source catalog semantics.
- `collect_runtime/*`
  - Owns normalized collection requests/results and project-aware execution orchestration.
- `crawlers/providers/*`
  - Owns provider-specific dispatch details and should hide provider transport/runtime differences.
- `discovery/*`
  - Owns discovery and candidate-finding loops, but should not become the canonical source registry.
- `ingest/*`
  - Owns downstream digestion and should consume normalized source outputs rather than provider-specific raw semantics.

This split is consistent with the currently confirmed contracts and keeps future source onboarding from scattering logic across unrelated layers.

### 5.3 Position of LLM crawler capabilities

The plan should avoid treating "LLM crawler" as a magic umbrella term.
In this repo it should be classified explicitly as one of:

- a provider implementation;
- a collection/runtime strategy;
- an enrichment layer attached to discovery or post-fetch processing.

Phase-1 should document the chosen role for each LLM-assisted capability instead of using the term generically.

### 5.4 Minimum source-to-ingest handoff semantics

The handoff from source layer to ingest should at minimum preserve:

- source identity:
  - channel/item/provider or equivalent stable identifiers;
- execution context:
  - `project_key`, query terms, or candidate URL origin when relevant;
- provenance:
  - original URL or canonical locator and acquisition path;
- quality trace:
  - minimum quality flags, dedupe hints, or review markers;
- routing intent:
  - whether the item is intended for direct ingest, pool write, or staged review.

This is a planning-level contract, not a claim that all fields already exist in one object today.

## 6. Implementation Order

The recommended phase-1 order is:

1. Freeze the current baseline inventory and the layer map.
2. Freeze the source tiering model and onboarding priority.
3. Freeze the boundary between source catalog, collect runtime, provider dispatch, and discovery.
4. Freeze minimum quality, dedupe, and stability rules.
5. Freeze directed-source onboarding strategy by source class.
6. Freeze the minimum handoff contract into ingest.

The point of this order is to avoid adding more sources before the system knows how to classify, route, and judge them.

## 7. Serial and Parallel Relationships

### 7.1 Serial work that should happen first

These items are serial prerequisites:

- baseline inventory before tiering;
- tiering and boundary freeze before large-scale source onboarding;
- minimum quality rules before onboarding high-volume or experimental sources;
- handoff definition before downstream automation depends on new sources.

### 7.2 Work that can run in parallel after the basics are frozen

After baseline, tiering, and boundaries are stable, these can progress in parallel:

- directed-source research by source family:
  - academic
  - business reports
  - business information
  - news
- quality-rule examples and exception handling design;
- handoff field mapping for ingest-facing consumers.

Parallel work is acceptable only after the layer boundaries are frozen.
Otherwise multiple subtracks will encode conflicting assumptions into the plan.

## 8. Minimum Validation

The next execution round should not start without at least the following checks:

- Structural validation:
  - confirm that the documented source layers map to real repo paths with:
  - `rg --files main/backend/app/services/source_library main/backend/app/services/collect_runtime main/backend/app/services/crawlers main/backend/app/services/discovery`
- Contract validation:
  - read and compare:
  - `main/backend/app/services/source_library/types.py`
  - `main/backend/app/services/collect_runtime/contracts.py`
  - `main/backend/app/services/crawlers/base.py`
- Flow validation:
  - trace one source example from source definition to collect request/result and then to downstream ingest entry assumptions.
- Governance validation:
  - document at least one case each for:
  - allow
  - downgrade or label
  - block
  based on quality or dedupe conditions.

## 9. Risks and Open Questions

### 9.1 Primary risks

- Adding sources before boundary freeze will keep multiplying duplicate logic.
- Treating all LLM crawler ideas as first-class mainline sources may distort the repo's current architecture.
- Leaving quality control mainly downstream will continue to push source noise into ingest and knowledge organization.

### 9.2 Open questions to resolve in the next round

- Which directed source families should be project-scoped versus global catalog entries?
- Which minimum metadata fields are mandatory before source output can enter ingest?
- Should quality gating be hard-blocking for some tiers and label-based for others?
- Where should LLM-assisted source expansion sit when it is partly discovery and partly extraction?

## 10. Phase Guidance

### Phase 1

Freeze the model:

- tiering;
- boundaries;
- quality rules;
- minimum handoff.

### Phase 2

Use the frozen model to onboard the first batch of directed high-value sources and any carefully bounded experimental crawlers.

### Phase 3

Refine automation:

- stronger evaluation;
- policy-driven ranking or downgrade;
- improved feedback from source-layer outcomes back into planning.
