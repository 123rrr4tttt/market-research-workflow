# Item Layering Boundary Constraints

Updated: 2026-03-26 PST

## Purpose

This note freezes one boundary for the current source-library path:

- `item` is an abstract source set.
- execution strategy is derived later.
- runtime diagnostics must not flow back and redefine item semantics.

The goal is to stop `item` objects from drifting into mixed config/runtime containers.

## Hard Constraints

1. `item` remains a source abstraction collection.
   - It may describe source identity, expected input shape, expected output shape, and stable grouping semantics.
   - It must not become a direct transport/parser/fallback control object.

2. A natural item may be discovered from the execution layer.
   - This is allowed only as a grouping/discovery mechanism.
   - Once materialized, the item still represents a source-set abstraction, not an execution plan.

3. Execution derivation is internal.
   - Route selection, adapter selection, API-vs-template split, slow-lane fallback, crawler preference, and frontdoor handoff belong to execution derivation or runtime.
   - These may be computed from an item, but they are not part of item meaning.

4. Runtime diagnostics are observational only.
   - Diagnostics may explain how one run executed.
   - Diagnostics must not be treated as stable item-definition fields.

## Layer Split

### 1. Item Layer

Allowed examples:

- source-set identity
- stable grouping meaning
- user-facing invocation contract
- accepted request inputs such as `query_terms`, `urls`, `domain`
- expected output type such as `candidate_urls`, `normalized_records`, `documents`

Not allowed here:

- parser profile
- adapter key
- fallback chain
- browser-deferred flags
- search-service routing knobs
- crawler-first knobs
- rollout/rollback switches

### 2. Execution Derivation Layer

Owned concerns:

- deriving source routes from an item
- splitting one logical source set into `search_template`, `official_access`, `rss`, `sitemap`, `url_routing`
- selecting adapter family per route
- assigning route-level fallback policy

This layer may produce natural executable groups, but those groups remain derived plans, not item semantics.

### 3. Runtime Diagnostics Layer

Owned concerns:

- actual search service used
- policy branch taken
- adapter branch taken
- fallback/degradation applied
- browser candidate deferral
- frontdoor handoff details
- per-run errors, timing, and counters

These belong in execution traces and result metadata, not in the stable item definition.

## Current Implication

For `handler.cluster.search_template`, the following interpretation is frozen:

- the item means “search-capable source cluster”
- `site_entries` and `official_access_site_entries` are execution-derived route buckets
- `arxiv` being rerouted to `official_access` is an execution concern, not a change in item meaning

## Field Placement Guidance

Keep on item side:

- `item_key`
- `name`
- stable grouping tags
- accepted user inputs
- expected source/output contract

Keep off item side:

- `search_template_adapter`
- `site_policy`
- `candidate_source_plan`
- `browser_candidate_deferred`
- `search_service_degraded_to`
- route-local parser and fallback details

## Enforcement Rule

Any future change that introduces a new item field must answer:

1. Does this field describe source-set meaning?
2. Or does it describe how one run executes?

If the answer is execution, it belongs outside the item definition.
