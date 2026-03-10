# Atomic Task List: Crawler Source Expansion (2026-03-07)

## Execution Status Snapshot

- `A1`: pending, baseline inventory and current layer map must be verified first.
- `A2-A3`: pending, source tiering and layer-boundary freeze are the first parallelizable design tasks.
- `A4-A5`: pending, quality governance and directed-source prioritization depend on the frozen model.
- `A6`: pending, ingest handoff definition closes the phase-1 system boundary.
- `A7`: pending, final validation and doc closure happen only after `A1-A6` are internally consistent.

## Global Serial-Parallel Rules

- L0 serial bootstrap:
  - `A1` must complete first.
- L1 parallel definition:
  - `A2` source tiering
  - `A3` layer boundary freeze
- L2 parallel governance:
  - `A4` quality/dedupe/stability rules
  - `A5` directed-source onboarding strategy
- L3 serial closure:
  - `A6` ingest handoff contract
  - `A7` validation and closure
- Conflict rule:
  - tasks that redefine the same contract vocabulary must merge serially before the next task starts;
  - no task may redefine `source_library`, `collect_runtime`, or `crawler provider` responsibilities independently after `A3` is frozen.

## Global Module Boundary

The task list assumes the following planning boundaries:

- Source catalog boundary:
  - `main/backend/app/services/source_library/*`
  owns source/channel/item semantics and routing metadata.
- Normalized collection boundary:
  - `main/backend/app/services/collect_runtime/*`
  owns `CollectRequest` and `CollectResult` style execution semantics.
- Provider boundary:
  - `main/backend/app/services/crawlers/*`
  and `main/backend/app/services/crawlers/providers/*`
  own provider dispatch and provider-specific runtime differences.
- Discovery boundary:
  - `main/backend/app/services/discovery/*`
  may discover candidates, but should not silently become the canonical source registry.
- Downstream consumer boundary:
  - `main/backend/app/services/ingest/*`
  consumes normalized handoff output and should not depend on provider-specific raw payload semantics.

## Global Deliverable Contract

Each task must produce:

- one explicit statement of what changed in the plan;
- one list of affected modules or source classes;
- one acceptance result;
- one minimum validation result or command.

Each task should avoid mixing all layers at once.
If a task cannot stay inside one planning concern, it is too large and should be split again.

## Task A1: Verify Baseline Inventory and Layer Map

- Goal: Confirm the current repo baseline, existing reusable contracts, and the minimum layer map used by the rest of the plan.
- status: pending
- depends_on: `[]`
- blocks: `["A2","A3"]`
- Input:
  - `main/backend/app/api/crawler.py`
  - `main/backend/app/api/source_library.py`
  - `main/backend/app/services/source_library/types.py`
  - `main/backend/app/services/collect_runtime/contracts.py`
  - `main/backend/app/services/crawlers/base.py`
  - current source-related service tree
- Output:
  - one verified baseline inventory
  - one confirmed layer map
  - one list of obvious gaps
- Acceptance:
  - the plan explicitly names what already exists in source catalog, collect runtime, crawler dispatch, discovery, and ingest-adjacent quality checks;
  - the baseline does not claim greenfield conditions where repo structure already exists.
- Minimum validation:
  - `rg --files main/backend/app/api main/backend/app/services | rg 'crawler|source_library|collect_runtime|discovery|ingest'`
- Module IO:
  - module_input_vars: `in_repo_paths(list)`, `in_contract_files(list)`
  - module_output_vars: `out_baseline(doc)`, `out_layer_map(doc)`, `out_gap_list(list)`
  - io_mapping: verified files -> baseline summary + layer map + gaps
  - io_boundary: documentation and repo inspection only

## Task A2: Freeze Source Tiering and Priority Model

- Goal: Define the source tiers and priority logic used to judge new source onboarding.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A4","A5"]`
- Input:
  - verified baseline inventory
  - current adapter families
  - target source classes:
    - academic
    - business reports
    - business information
    - news
- Output:
  - one tier model with stable names
  - one priority rationale for each target source class
  - one explicit list of non-default experimental sources
- Acceptance:
  - the plan distinguishes baseline platform sources, directed high-value sources, and experimental/augmentation sources;
  - each target source class is placed into a tier with a reason, not only a label.
- Minimum validation:
  - review that every target source class has:
  - tier
  - reason
  - initial onboarding priority
- Module IO:
  - module_input_vars: `in_baseline(obj)`, `in_source_classes(list)`, `in_priority_signals(list)`
  - module_output_vars: `out_tiers(list)`, `out_priority_table(table)`, `out_experimental_list(list)`
  - io_mapping: source classes + baseline -> tier model + priority table
  - io_boundary: tiering and prioritization rules only

## Task A3: Freeze Layer Responsibilities and Onboarding Boundary

- Goal: Define which layer owns source definitions, normalized execution, provider dispatch, discovery, and downstream handoff preparation.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A4","A5","A6"]`
- Input:
  - `ChannelRecord`
  - `SourceItemRecord`
  - `FrontDoorExecutionProtocol`
  - `CollectRequest`
  - `CollectResult`
  - `CrawlerDispatchRequest`
  - `CrawlerDispatchResult`
- Output:
  - one responsibility table for `source_library`, `collect_runtime`, `crawlers/providers`, `discovery`, and `ingest` boundary expectations
  - one minimal onboarding path for a new source or crawler capability
  - one statement of where LLM-assisted crawling belongs case by case
- Acceptance:
  - the plan can explain where a new source definition is registered;
  - the plan can explain where a new provider-specific runtime is implemented;
  - discovery is not treated as the canonical replacement for source cataloging.
- Minimum validation:
  - compare the responsibility table against:
  - `main/backend/app/services/source_library/types.py`
  - `main/backend/app/services/collect_runtime/contracts.py`
  - `main/backend/app/services/crawlers/base.py`
- Module IO:
  - module_input_vars: `in_source_contracts(list)`, `in_runtime_contracts(list)`, `in_provider_contracts(list)`
  - module_output_vars: `out_boundary_table(table)`, `out_onboarding_flow(doc)`, `out_llm_role_map(table)`
  - io_mapping: current contracts -> boundary table + onboarding flow + LLM role map
  - io_boundary: source-layer responsibility split only

## Task A4: Define Minimum Quality, Dedupe, and Stability Rules

- Goal: Specify the minimum governance rules that must exist before bulk source expansion.
- status: pending
- depends_on: `["A2","A3"]`
- blocks: `["A6","A7"]`
- Input:
  - source tier model
  - boundary table
  - current quality anchors:
    - `main/backend/app/services/ingest/meaningful_gate.py`
    - `main/backend/app/services/resource_pool/llm_validator.py`
    - `main/backend/app/services/source_library/resolver.py`
    - `main/backend/app/services/discovery/store.py`
- Output:
  - one minimum rule set for:
    - reliability
    - repeatability
    - content signal
    - dedupe
    - metadata completeness
  - one allow/downgrade/block policy shape
- Acceptance:
  - the plan states which checks should happen at source-layer time and which can remain downstream;
  - the plan includes at least one downgrade-or-label path, not only pass/fail.
- Minimum validation:
  - document one example each for:
  - allow
  - downgrade
  - block
- Module IO:
  - module_input_vars: `in_tiers(list)`, `in_boundary_table(table)`, `in_quality_anchors(list)`
  - module_output_vars: `out_rule_set(doc)`, `out_policy_matrix(table)`, `out_examples(list)`
  - io_mapping: tiers + boundaries + anchors -> minimum governance rules + policy matrix
  - io_boundary: governance rules only

## Task A5: Define Directed-Source Onboarding Strategy

- Goal: Decide the first-wave onboarding strategy for directed source families without pretending the entire external source universe is already fixed.
- status: pending
- depends_on: `["A2","A3"]`
- blocks: `["A6","A7"]`
- Input:
  - source tier model
  - boundary table
  - target source families:
    - academic
    - business reports
    - business information
    - news
- Output:
  - one first-wave onboarding order
  - one reason for that order
  - one note on whether each family is global-catalog first or project-scoped first
- Acceptance:
  - the plan does not collapse all directed sources into one bucket;
  - high-value/high-cost and high-frequency/high-noise sources are treated differently.
- Minimum validation:
  - review that each target family has:
  - onboarding order
  - governance note
  - catalog scope note
- Module IO:
  - module_input_vars: `in_tiers(list)`, `in_source_families(list)`, `in_scope_options(list)`
  - module_output_vars: `out_wave_plan(table)`, `out_scope_notes(list)`, `out_priority_rationale(list)`
  - io_mapping: source families + tier model -> onboarding order + scope notes + rationale
  - io_boundary: directed-source strategy only

## Task A6: Freeze Minimum Source-to-Ingest Handoff Contract

- Goal: Define what the source layer must hand to ingest so downstream processing does not rely on provider-specific internals.
- status: pending
- depends_on: `["A3","A4","A5"]`
- blocks: `["A7"]`
- Input:
  - boundary table
  - quality policy matrix
  - directed-source onboarding strategy
  - existing handoff-related semantics in `FrontDoorExecutionProtocol`, `CollectResult`, and ingest services
- Output:
  - one minimum handoff field set
  - one explanation of what is mandatory versus optional
  - one explicit statement of what remains downstream-only
- Acceptance:
  - the handoff definition preserves source identity, execution context, provenance, and quality trace;
  - the plan does not leak provider raw payload requirements into ingest-facing semantics.
- Minimum validation:
  - trace one example source through:
  - source definition
  - collect request/result
  - ingest-facing handoff assumptions
- Module IO:
  - module_input_vars: `in_boundary_table(table)`, `in_policy_matrix(table)`, `in_handoff_candidates(list)`
  - module_output_vars: `out_handoff_fields(list)`, `out_required_optional_map(table)`, `out_downstream_exclusions(list)`
  - io_mapping: boundaries + policy + contracts -> handoff field set + required/optional map
  - io_boundary: source-to-ingest handoff only

## Task A7: Validation Pack and Documentation Closure

- Goal: Close the phase-1 planning round with a coherent validation pack and no unresolved contradictions across the main plan and atomic task list.
- status: pending
- depends_on: `["A4","A5","A6"]`
- blocks: `[]`
- Input:
  - main plan document
  - completed task outputs from `A1-A6`
- Output:
  - one consistency-checked plan snapshot
  - one minimum validation checklist
  - one residual-risk list
- Acceptance:
  - the main plan and task list use the same vocabulary for tiers, boundaries, and validation;
  - at least one structural validation and one flow validation are present.
- Minimum validation:
  - `git diff --check -- development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/01_crawler-source-expansion-plan-2026-03-07.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/02_atomic-tasklist-crawler-source-expansion-2026-03-07.md`
- Module IO:
  - module_input_vars: `in_plan_doc(file)`, `in_task_outputs(list)`
  - module_output_vars: `out_consistent_plan(bool)`, `out_validation_pack(doc)`, `out_residual_risks(list)`
  - io_mapping: completed planning outputs -> consistent plan snapshot + validation pack + risks
  - io_boundary: target planning documents only
