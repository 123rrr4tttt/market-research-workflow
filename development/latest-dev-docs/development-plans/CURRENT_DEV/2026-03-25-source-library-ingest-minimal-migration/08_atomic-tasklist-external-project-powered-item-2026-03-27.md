# Atomic Task List: External Project Powered Item (2026-03-27)

## Execution Status Snapshot

- `AT-EXT-01`: pending, external-item scope and boundary freeze.
- `AT-EXT-02`: pending, manifest contract freeze.
- `AT-EXT-03`: pending, provider registry skeleton.
- `AT-EXT-04`: pending, manifest builder pipeline.
- `AT-EXT-05`: pending, provider runner implementation.
- `AT-EXT-06`: pending, frontdoor adapter mapping.
- `AT-EXT-07`: pending, item registration and listing exposure.
- `AT-EXT-08`: pending, runtime execution path.
- `AT-EXT-09`: pending, validation closure.

## Reference Pack

- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [06_atomic-tasklist-item-layering-migration-2026-03-27.md](./06_atomic-tasklist-item-layering-migration-2026-03-27.md)
- [07_validation-closure-item-layering-migration-2026-03-27.md](./07_validation-closure-item-layering-migration-2026-03-27.md)
- [references/2026-03-26-item-layering-boundary-constraints.md](./references/2026-03-26-item-layering-boundary-constraints.md)
- [references/2026-03-27-external-project-powered-item-design.md](./references/2026-03-27-external-project-powered-item-design.md)
- [references/INDEX.md](./references/INDEX.md)

## Serial-Parallel Rules

- L0 serial discovery freeze:
  - `AT-EXT-01`
  - `AT-EXT-02`
- L1 parallel foundation build:
  - `AT-EXT-03` provider registry skeleton
  - `AT-EXT-04` manifest builder pipeline
- L2 serial execution spine:
  - `AT-EXT-05` provider runner implementation
  - `AT-EXT-06` frontdoor adapter mapping
- L3 serial exposure layer:
  - `AT-EXT-07` item registration and listing exposure
- L4 serial runtime path:
  - `AT-EXT-08` runtime execution path
- L5 serial closure:
  - `AT-EXT-09` validation closure

## Global Acceptance Contract

- An external project powered item is still an item-level abstraction, not a repo snapshot or an execution config blob.
- The project link is only a registration input. Runtime execution must consume a stable manifest, not re-parse arbitrary repositories on every query.
- The manifest is the source of truth for supported inputs, execution modes, capabilities, provenance, and normalization mapping.
- The system must support at least these external project classes in the first version:
  - feed / route aggregators such as `RSSHub`, `RSS-Bridge`, or existing RSS exports
  - article extraction stacks such as `Fundus` or `news-please`
  - API/provider wrappers such as `OpenBB`-style providers
- Arbitrary repo code must not be executed in-process by default.
- The final user-facing output must still land in the existing frontdoor envelope and preserve current standardized fields.
- Built-in source-library items and their current contracts must remain backward-compatible during this work.

## Task AT-EXT-01: Freeze External-Item Scope and Boundary Contract

- Goal: Freeze what an external project powered item is allowed to represent, and what it is not allowed to become.
- Status: pending
- Depends_on: `[]`
- Blocks: `["AT-EXT-02","AT-EXT-03","AT-EXT-04","AT-EXT-05","AT-EXT-06","AT-EXT-07","AT-EXT-08","AT-EXT-09"]`
- Input:
  - [references/2026-03-26-item-layering-boundary-constraints.md](./references/2026-03-26-item-layering-boundary-constraints.md)
  - `main/backend/app/services/source_library/item_plan.py`
  - `main/backend/app/services/source_library/resolver.py`
  - current source-library frontdoor and runtime adapter paths
- Output:
  - frozen external-item boundary note
  - keep / move / reject decisions for:
    - project link
    - project metadata
    - manifest reference
    - provider mode
    - runtime diagnostics
  - explicit non-goals for runtime repo parsing and arbitrary code execution
- Acceptance:
  - the boundary note makes it clear that an external project link is only a registration seed, not the item definition itself.
- Minimum validation:
  - `rg -n "external item|manifest|provider runner|frontdoor adapter|runtime diagnostics" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration -S`

## Task AT-EXT-02: Freeze Manifest Contract

- Goal: Define the stable manifest schema that can represent an external project without binding the system to a single project shape.
- Status: pending
- Depends_on: `["AT-EXT-01"]`
- Blocks: `["AT-EXT-03","AT-EXT-04","AT-EXT-05","AT-EXT-06","AT-EXT-07","AT-EXT-08","AT-EXT-09"]`
- Input:
  - boundary note from `AT-EXT-01`
  - current source-library execution plan structure
  - existing frontdoor standardized output fields
- Output:
  - manifest contract v1 with fields for:
    - project identity and provenance
    - supported execution modes
    - accepted input shapes
    - capability flags
    - normalization mapping
    - refresh / cache policy
    - safety and sandbox hints
  - explicit contract for what must be deterministic versus LLM-assisted
- Acceptance:
  - the manifest is sufficient to route execution without re-reading the source repository on every run.
- Minimum validation:
  - `rg -n "manifest contract|supported execution modes|normalization mapping|refresh policy|sandbox" development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-25-source-library-ingest-minimal-migration -S`

## Task AT-EXT-03: Build Provider Registry Skeleton

- Goal: Create the registry that maps manifest-declared capabilities to concrete provider adapters.
- Status: pending
- Depends_on: `["AT-EXT-02"]`
- Blocks: `["AT-EXT-04","AT-EXT-05","AT-EXT-06","AT-EXT-07","AT-EXT-08","AT-EXT-09"]`
- Input:
  - manifest contract v1
  - current source-library adapter registry patterns
- Output:
  - provider registry keyed by provider kind and capability family
  - first-class provider categories such as:
    - feed / route aggregator
    - site extractor
    - article body extractor
    - API provider
    - local library wrapper
    - container / service runner
- Acceptance:
  - registry resolution is separate from manifest construction and separate from runtime execution.
- Minimum validation:
  - `rg -n "provider registry|provider kind|capability family|adapter registry" main/backend/app -S`

## Task AT-EXT-04: Build Manifest Builder Pipeline

- Goal: Turn a project link into a stable manifest draft that can be reviewed, stored, and later executed.
- Status: pending
- Depends_on: `["AT-EXT-02","AT-EXT-03"]`
- Blocks: `["AT-EXT-05","AT-EXT-06","AT-EXT-07","AT-EXT-08","AT-EXT-09"]`
- Input:
  - manifest contract v1
  - provider registry skeleton
  - project link / repo / docs source
- Output:
  - manifest builder pipeline that can:
    - probe repository metadata
    - detect likely execution mode
    - extract declared inputs / outputs
    - produce a normalized manifest draft
  - explicit confidence / uncertainty markers for LLM-assisted fields
- Acceptance:
  - identical project links yield the same manifest family unless the source itself changes.
  - uncertain fields are marked, not silently guessed as stable truth.
- Minimum validation:
  - `rg -n "manifest builder|project probe|confidence|uncertainty|draft manifest" main/backend/app -S`

## Task AT-EXT-05: Implement Provider Runner

- Goal: Execute a manifest using a bounded provider runtime instead of ad hoc source-specific code paths.
- Status: pending
- Depends_on: `["AT-EXT-03","AT-EXT-04"]`
- Blocks: `["AT-EXT-06","AT-EXT-07","AT-EXT-08","AT-EXT-09"]`
- Input:
  - provider registry skeleton
  - manifest builder output
  - current source-library runtime adapters
- Output:
  - provider runner interface for supported modes
  - explicit execution modes such as:
    - HTTP API
    - RSS / feed fetch
    - sitemap crawl
    - browser-page fetch
    - local Python library wrapper
    - container or service wrapper
- Acceptance:
  - the runner consumes only the manifest plus runtime input payload.
  - arbitrary repo code is not executed in-process by default.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py`

## Task AT-EXT-06: Add Frontdoor Adapter Mapping

- Goal: Map provider output into the existing standardized frontdoor envelope without changing frontdoor semantics.
- Status: pending
- Depends_on: `["AT-EXT-05"]`
- Blocks: `["AT-EXT-07","AT-EXT-08","AT-EXT-09"]`
- Input:
  - provider runner output
  - current `frontdoor_ingress` and `postprocess_frontdoor` contracts
  - current terminal-output shape
- Output:
  - adapter that can map:
    - candidate URLs
    - article metadata
    - article body
    - PDF artifact metadata
    - provider diagnostics
  - standardized handoff into frontdoor without inventing a new envelope family
- Acceptance:
  - a successful provider run can be forwarded through the existing standardized output path.
  - optional PDF artifacts can ride along as first-class outputs when the provider supplies them.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_postprocess_frontdoor_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`

## Task AT-EXT-07: Register and List External Items

- Goal: Expose external project powered items through the same user-facing listing surface as built-in source items.
- Status: pending
- Depends_on: `["AT-EXT-04","AT-EXT-06"]`
- Blocks: `["AT-EXT-08","AT-EXT-09"]`
- Input:
  - manifest builder output
  - frontdoor adapter mapping
  - current item listing and definition-first item surface
- Output:
  - registration flow for external project links
  - listing flow that shows external items as abstract item entries
  - explicit opt-in path for execution-plan / runtime debug expansion if needed
- Acceptance:
  - users can treat external items like regular source-library items during invocation.
  - external implementation details remain hidden unless explicitly requested.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_source_library_resolver_unittest.py`

## Task AT-EXT-08: Wire Runtime Execution Path

- Goal: Make a registered external item runnable end-to-end through the source-library execution path.
- Status: pending
- Depends_on: `["AT-EXT-05","AT-EXT-06","AT-EXT-07"]`
- Blocks: `["AT-EXT-09"]`
- Input:
  - registered external item
  - manifest
  - provider runner
  - frontdoor adapter
- Output:
  - runtime execution path from user input to candidate generation and standardized output
  - runtime diagnostics for provider selection, failure mode, and fallbacks
- Acceptance:
  - the execution path is invoked through the item surface, not through a one-off special command.
  - the runtime result remains compatible with current source-library output handling.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_resource_pool_unified_search_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`

## Task AT-EXT-09: Run Validation Closure

- Goal: Close the external-project powered item round with regression evidence and documentation consistency.
- Status: pending
- Depends_on: `["AT-EXT-08"]`
- Blocks: `[]`
- Input:
  - completed outputs from `AT-EXT-01 ~ AT-EXT-08`
  - current source-library reference pack
  - current item layering boundary note
- Output:
  - validation closure note
  - regression pack summary
  - explicit residual-risk matrix for:
    - repo parsing drift
    - provider capability mismatch
    - execution sandboxing
    - frontdoor mapping gaps
    - unsupported project classes
- Acceptance:
  - the closure note states exactly which classes of external projects are supported in v1 and which remain out of scope.
- Minimum validation:
  - `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_source_library_item_resolver_unittest.py main/backend/tests/unit/test_resource_pool_unified_search_unittest.py main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`
