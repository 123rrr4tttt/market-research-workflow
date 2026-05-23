# Atomic Task List: Typed Knowledge Organization (2026-03-07)

## Execution Status Snapshot

- `K1-K2`: pending, baseline freeze and object-boundary freeze are the first serial gate.
- `K3-K5`: pending, governance semantics, topic/booklet semantics, and downstream contract can run in parallel after `K2`.
- `K6`: pending, automation and manual-governance workflow depends on the earlier model decisions.
- `K7`: pending, one sample scenario and validation pack closes the planning loop.
- `K8`: pending, final review checks consistency across the two planning docs.

## Global Serial-Parallel Rules

- `L0` serial bootstrap: `K1 -> K2`
- `L1` parallel design layer after `K2`:
  - `group-a`: `K3`
  - `group-b`: `K4`
  - `group-c`: `K5`
- `L2` serial workflow layer: `K6` waits for `K3-K5`
- `L3` serial closure: `K7 -> K8`
- File-conflict rule:
  - all tasks write only within this directory
  - if two tasks need the same markdown file, merge their outputs in one pass before continuing

## Global Module Boundary

- Allowed read scope:
  - the two documents in this directory
  - relevant repo code and docs used as evidence for baseline claims
- Allowed write scope:
  - only the markdown files in this directory
- Disallowed actions:
  - changing source code
  - changing index files
  - inventing implementation facts that are not supported by current repo structure

## Global Planning Output Contract

Each task must return:

- `result`: what decision or artifact was produced
- `changed_files`: which planning files need updates
- `verification_status`: what minimum check was performed
- `risk`: what remains uncertain or intentionally deferred

Each task must also declare:

- `module_input_vars`
- `module_output_vars`
- `io_mapping`
- `io_boundary`

## Task K1: Baseline Inventory and Terminology Freeze

- Objective: verify the current repo surfaces that already touch organization concepts and freeze the glossary used by this topic.
- status: pending
- depends_on: `[]`
- blocks: `["K2"]`
- Input:
  - `01_typed-knowledge-organization-plan-2026-03-07.md`
  - `main/backend/app/api/topics.py`
  - `main/backend/app/services/discovery/store.py`
  - `main/backend/app/services/resource_pool/auto_classify.py`
  - `main/backend/app/services/graph/doc_types.py`
  - `main/backend/app/api/writing.py`
- Output:
  - one baseline table
  - one glossary for `Type Node`, `Knowledge Item`, `Topic Cluster`, `Booklet`
  - one gap list
- Acceptance:
  - every baseline claim is tied to an existing repo path
  - the glossary avoids using the same term for taxonomy, topic grouping, and graph projection
- Minimal verification:
  - reread the cited repo files and confirm the plan doc does not claim a missing feature that already exists
- Module IO:
  - module_input_vars: `in_plan_doc(file)`, `in_repo_refs(list)`, `in_existing_terms(list)`
  - module_output_vars: `out_baseline_table(doc)`, `out_glossary(list)`, `out_gap_list(list)`
  - io_mapping: repo refs + existing terms -> baseline table + glossary + gap list
  - io_boundary: docs in this directory only

## Task K2: Core Object Boundary Definition

- Objective: define the minimum responsibility boundary for `Type Node`, `Knowledge Item`, `Topic Cluster`, and `Booklet`.
- status: pending
- depends_on: `["K1"]`
- blocks: `["K3","K4","K5"]`
- Input:
  - `K1` glossary and gap list
  - parent planning requirements from `../2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md`
- Output:
  - one object-responsibility matrix
  - one relationship table
  - one list of Phase-1 constraints
- Acceptance:
  - `Type Node` is not defined as a graph-rendering node
  - `Booklet` is not used as a synonym for taxonomy
  - `Topic Cluster` is not reduced to a free-form tag bucket
  - at least one Phase-1 simplification is explicit, such as single-primary-parent or single-primary-type assumptions
- Minimal verification:
  - perform a terminology consistency pass against both planning files
- Module IO:
  - module_input_vars: `in_glossary(list)`, `in_parent_requirements(doc)`, `in_gap_list(list)`
  - module_output_vars: `out_object_matrix(table)`, `out_relationships(table)`, `out_phase1_constraints(list)`
  - io_mapping: glossary + requirements + gaps -> object matrix + relationships + constraints
  - io_boundary: docs in this directory only

## Task K3: Governance Dimension Definition

- Objective: place `review_state`, `quality_grade`, `locale`, and provenance in the correct layer and define their minimum semantics.
- status: pending
- depends_on: `["K2"]`
- blocks: `["K6","K7"]`
- Input:
  - `K2` object-boundary outputs
  - current repo evidence about project-scoped flows and downstream consumers
- Output:
  - one governance-dimension matrix
  - one minimum update-rule set
  - one note about Phase-1 exclusions
- Acceptance:
  - quality grade is defined as governance metadata, not taxonomy
  - bilingual support is assigned a concrete Phase-1 representation strategy
  - provenance is required for organized knowledge outputs
- Minimal verification:
  - confirm each governance dimension maps to an object layer, attribute layer, or workflow layer instead of remaining ambiguous
- Module IO:
  - module_input_vars: `in_object_matrix(table)`, `in_repo_constraints(list)`, `in_downstream_needs(list)`
  - module_output_vars: `out_governance_matrix(table)`, `out_update_rules(list)`, `out_exclusions(list)`
  - io_mapping: object matrix + constraints + needs -> governance matrix + update rules + exclusions
  - io_boundary: docs in this directory only

## Task K4: Topic Cluster and Booklet Semantics

- Objective: define how topic clustering and booklet organization differ, interact, and remain stable for downstream consumers.
- status: pending
- depends_on: `["K2"]`
- blocks: `["K6","K7"]`
- Input:
  - `K2` object-responsibility matrix
  - baseline consumer paths in graph and writing surfaces
- Output:
  - one topic-vs-booklet comparison table
  - one lifecycle note for membership and curation
  - one list of downstream usage examples
- Acceptance:
  - the document makes it clear whether topic membership is thematic and whether booklet membership is curated
  - downstream examples include at least one graph-facing or writing-facing use case
  - the semantics do not require schema details to be useful
- Minimal verification:
  - run a wording pass to ensure no section uses `topic`, `booklet`, and `type node` interchangeably
- Module IO:
  - module_input_vars: `in_object_matrix(table)`, `in_consumer_examples(list)`, `in_baseline_paths(list)`
  - module_output_vars: `out_comparison_table(table)`, `out_membership_rules(list)`, `out_usage_examples(list)`
  - io_mapping: object matrix + consumer examples -> comparison + rules + examples
  - io_boundary: docs in this directory only

## Task K5: Minimum Downstream Contract Draft

- Objective: draft the minimum read contract that search, graph, writing, and reporting can rely on.
- status: pending
- depends_on: `["K2"]`
- blocks: `["K6","K7"]`
- Input:
  - `K2` object boundaries
  - baseline consumer files:
    - `main/backend/app/api/writing.py`
    - `main/backend/app/api/llm_report.py`
    - `main/backend/app/services/graph/doc_types.py`
    - `main/frontend-modern/src/pages/GraphPage.tsx`
    - `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
- Output:
  - one minimum field list
  - one consumer mapping table
  - one note on what is intentionally not fixed in Phase 1
- Acceptance:
  - all downstream readers are described as consumers of stable keys plus organization metadata
  - the contract does not leak graph-only or writing-only assumptions into the shared core
  - the draft remains implementation-agnostic enough to guide later API work
- Minimal verification:
  - compare the shared contract draft against each listed consumer and record any mismatch or missing field
- Module IO:
  - module_input_vars: `in_object_boundaries(table)`, `in_consumer_files(list)`, `in_phase1_constraints(list)`
  - module_output_vars: `out_field_list(list)`, `out_consumer_matrix(table)`, `out_phase1_omissions(list)`
  - io_mapping: boundaries + consumer files -> field list + consumer matrix + omissions
  - io_boundary: docs in this directory only

## Task K6: Automation and Manual Governance Workflow

- Objective: define the minimum workflow for candidate generation, human confirmation or override, and downstream visibility.
- status: pending
- depends_on: `["K3","K4","K5"]`
- blocks: `["K7"]`
- Input:
  - governance semantics from `K3`
  - topic/booklet semantics from `K4`
  - downstream contract from `K5`
  - automation pattern reference from `main/backend/app/services/resource_pool/auto_classify.py`
- Output:
  - one step-by-step workflow
  - one decision table for auto vs manual ownership
  - one failure-path note
- Acceptance:
  - the workflow distinguishes candidate generation from final acceptance
  - human override semantics are explicit
  - downstream read visibility is tied to governance state, not left implicit
- Minimal verification:
  - the workflow can be narrated from input evidence to downstream consumer without inventing missing object types mid-stream
- Module IO:
  - module_input_vars: `in_governance_matrix(table)`, `in_contract_fields(list)`, `in_automation_pattern(doc)`
  - module_output_vars: `out_workflow(list)`, `out_decision_table(table)`, `out_failure_notes(list)`
  - io_mapping: governance + contract + automation pattern -> workflow + ownership table + failure notes
  - io_boundary: docs in this directory only

## Task K7: Example Scenario and Validation Pack

- Objective: prove the planning model is usable by walking one concrete example end to end.
- status: pending
- depends_on: `["K3","K4","K5","K6"]`
- blocks: `["K8"]`
- Input:
  - outputs from `K3-K6`
- Output:
  - one end-to-end example
  - one structural validation checklist
  - one process validation checklist
- Acceptance:
  - the example includes evidence source, knowledge item, type node, topic cluster, optional booklet, governance metadata, and one downstream consumer
  - the example contains one automation proposal and one human confirmation step
  - the validation checklist is specific enough for later implementers to reuse
- Minimal verification:
  - check that the example does not contradict any earlier task output
- Module IO:
  - module_input_vars: `in_governance_outputs(obj)`, `in_semantics_outputs(obj)`, `in_contract_outputs(obj)`, `in_workflow_outputs(obj)`
  - module_output_vars: `out_example(doc)`, `out_structural_checklist(list)`, `out_process_checklist(list)`
  - io_mapping: prior outputs -> example + validation checklists
  - io_boundary: docs in this directory only

## Task K8: Planning Closure Review

- Objective: perform the final coherence pass across the main plan and the atomic task list.
- status: pending
- depends_on: `["K7"]`
- blocks: `[]`
- Input:
  - `01_typed-knowledge-organization-plan-2026-03-07.md`
  - `02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md`
- Output:
  - one final consistency pass
  - one unresolved-question list
  - one minimal handoff note for the next implementer
- Acceptance:
  - both files use the same terminology and phase order
  - every required section from the parent writing standard is present
  - unresolved questions are explicit instead of hidden as vague prose
- Minimal verification:
  - run `git diff --check -- 01_typed-knowledge-organization-plan-2026-03-07.md 02_atomic-tasklist-typed-knowledge-organization-2026-03-07.md`
- Module IO:
  - module_input_vars: `in_main_plan(file)`, `in_atomic_tasklist(file)`
  - module_output_vars: `out_consistency_status(str)`, `out_open_questions(list)`, `out_handoff_note(doc)`
  - io_mapping: main plan + tasklist -> closure status + open questions + handoff note
  - io_boundary: docs in this directory only
