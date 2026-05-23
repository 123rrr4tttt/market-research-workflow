<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排/02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Atomic Task List: Abstract Planning Folderization (2026-03-07)

## Execution Status Snapshot

- `A1`: closed / wave15_verified, freeze the mother-document to topic-directory ownership map.
- `A2`: closed / wave15_verified, freeze the canonical child-directory document contract.
- `A3`: closed / wave15_verified, normalize topic `01_*` plan documents against the frozen contract.
- `A4`: closed / wave15_verified, normalize topic `02_*` atomic task documents after each `01_*` scope is stable.
- `A5`: closed / wave15_verified, run cross-topic dependency and coverage review.
- `A6`: closed / wave15_verified, prepare external handoff for index synchronization without editing index files inside this work package.

Wave15 supersedes the earlier pending snapshot for this coordination package:
`scripts/check_abstract_planning_folderization.py --strict-content` is now the
authoritative repeatable gate for the folderization contract.

## Global Serial-Parallel Rules

- L0 serial bootstrap: `A1 -> A2`.
- L1 parallel planning: after `A2`, each topic directory may normalize its `01_*` document independently.
- L2 serial within one topic: `A3(topic)` must complete before `A4(topic)`.
- L3 parallel tasking: once a topic `01_*` is stable, its `02_*` can be normalized independently of other topics.
- L4 serial closure: `A5 -> A6`.

## Cross-Topic Layered Execution Order (Operationalized)

Use the following order when turning topic plans into real execution.

- Layer-0 (serial): run this coordination package first: `A1 -> A2`.
- Layer-1 (parallel by topic): run each topic bootstrap wave after Layer-0 exits.
- Layer-2 (parallel by topic, serial within topic): run each topic core wave by its own DAG.
- Layer-3 (serial-dominant integration): align cross-topic dependencies and contracts.
- Layer-4 (serial closure): run cross-topic regression gate and external handoff.

### Layer Entry/Exit Gates

- Layer-0 entry:
  - coordination doc set is present;
  - active topics are frozen.
- Layer-0 exit:
  - ownership map is stable;
  - child document contract is frozen.
- Layer-1 entry:
  - Layer-0 exited;
  - each topic has one owner.
- Layer-1 exit:
  - topic bootstrap tasks are complete;
  - topic boundaries are explicit.
- Layer-2 entry:
  - each topic bootstrap output is accepted.
- Layer-2 exit:
  - each topic produced a consistent task graph and minimum validation set.
- Layer-3 entry:
  - Graph, LLM, Writing, Topology, and i18n themes all reached their mid-stage contract outputs.
- Layer-3 exit:
  - cross-topic dependency alignment is recorded and accepted.
- Layer-4 entry:
  - Layer-3 alignment accepted;
  - no unresolved ownership drift.
- Layer-4 exit:
  - minimum regression closure is complete;
  - external sync handoff is ready.

## Wave Model by Topic (Execution-Ready)

- `crawler-source-expansion`:
  - wave-0: `A1`
  - wave-1: `A2`, `A3`
  - wave-2: `A4`, `A5`
  - wave-3: `A6`
  - wave-4: `A7`
- `ingest-digestion-and-long-cycle-automation`:
  - wave-0: `A1`
  - wave-1: `A2`, `A4`
  - wave-2: `A3`, `A5`
  - wave-3: `A6`
  - wave-4: `A7`
  - wave-5: `A8`
- `typed-knowledge-organization`:
  - wave-0: `K1`
  - wave-1: `K2`
  - wave-2: `K3`, `K4`, `K5`
  - wave-3: `K6`
  - wave-4: `K7`
  - wave-5: `K8`
- `llm-service-and-agent-platformization`:
  - wave-0: `A1`
  - wave-1: `A2`, `A3`, `A4`
  - wave-2: `A5`
  - wave-3: `A6`
  - wave-4: `A7`
  - wave-5: `A8`
- `graph-editing-and-reporting`:
  - wave-0: `A1`
  - wave-1: `A2`
  - wave-2: `A3`, `A5`
  - wave-3: `A4`, `A6`
  - wave-4: `A7`
- `writing-workbench-evolution`:
  - wave-0: `E1`
  - wave-1: `E2`
  - wave-2: `E3`, `E4`, `E5`, `E6`
  - wave-3: `E7`, `E8`
  - wave-4: `E9`
- `dual-frontend-workbench-topology`:
  - wave-0: `A1`
  - wave-1: `A2`
  - wave-2: `A3`, `A5`
  - wave-3: `A4`
  - wave-4: `A6`
  - wave-5: `A7`
  - wave-6: `A8`
- `frontend-i18n-theme-modularization`:
  - wave-0: `A1`
  - wave-1: `A2`, `A3`, `A4`
  - wave-2: `A5`
  - wave-3: `A6`, `A7`, `A8`
  - wave-4: `A9`
  - wave-5: `A10`

## Cross-Theme Hard Dependencies

- `writing E3` waits for `graph A5` and aligns with `graph A6`.
- `writing E6` aligns with `llm A2`, `llm A4`, and `llm A6`.
- `writing E8` is the explicit cross-theme contract merge point and must run before final closures.

## Same-Layer Parallel Dispatch Template

- max_parallel_workers:
  - Layer-0: `1`
  - Layer-1: `3`
  - Layer-2: `4`
  - Layer-3: `3`
  - Layer-4: `1`
- file-lock hot spots (must be serial):
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/frontend-modern/src/pages/SettingsPage.tsx`
  - `main/frontend-modern/src/index.css`
- retry policy:
  - transient failures: max 2 retries;
  - dependency/contract failures: no blind retry, fix upstream first.

## One-Week Execution Cadence (Day1-Day7)

- Day-1: Layer-0 complete (`A1 -> A2`).
- Day-2: Layer-1 topic bootstraps.
- Day-3: Layer-2 core contract waves (first half).
- Day-4: Layer-2 core contract waves (second half) and lock-map refresh.
- Day-5: Layer-3 integration prep (`writing E3/E6` dependency alignment in place).
- Day-6: Layer-3 merge (`writing E8`) and pre-closure checks.
- Day-7: Layer-4 closure (`A5 -> A6`) and external handoff.

Conflict rules:

- Two agents must not edit the same topic document at the same time.
- A topic directory may be normalized independently, but it must not redefine another topic's primary ownership.
- Upper-level indexes are an external follow-up step; do not mix those edits into this directory-local normalization package.

## Global Module Boundary

### Working Modules

- `module_source`: `抽象规划.md` as the mother requirement source.
- `module_coordination`: this directory's `01_*` and `02_*` documents.
- `module_topic_dirs`: topic-specific directories under `CURRENT_DEV`.

### External Modules

- upper-level navigation and index files;
- product code, API contracts, UI implementation, and runtime tasks;
- closed/archive directories outside `CURRENT_DEV`.

### Global IO Contract

- `module_input_vars`:
  - `in_mother_doc(file)`
  - `in_repo_doc_norms(doc)`
  - `in_existing_topic_dirs(list)`
  - `in_topic_docs(list)`
- `module_output_vars`:
  - `out_topic_map(table)`
  - `out_plan_contract(checklist)`
  - `out_normalized_plan_docs(list)`
  - `out_normalized_task_docs(list)`
  - `out_validation_report(checklist)`
  - `out_external_handoff(note)`
- `io_boundary`:
  - allowed write scope is topic-planning documentation;
  - index synchronization is documented as handoff only unless explicitly assigned in a separate task.

## Task A1: Freeze Topic Ownership Map

- Goal: convert the mother document into one stable ownership map from requirements to topic directories.
- status: closed / wave15_verified
- depends_on: `[]`
- blocks: `["A2","A3","A4","A5"]`
- Input:
  - `抽象规划.md`
  - current `CURRENT_DEV` topic directory set
  - repository naming/date rules from `development/latest-dev-docs/README.md`
- Output:
  - one approved topic list
  - one ownership map for major requirement clusters
  - one overlap note for cross-topic dependencies
- Acceptance:
  - each major requirement cluster has exactly one primary topic owner
  - overlap is represented as dependency, not duplicated ownership
  - no new topic is introduced without a clear overload reason
- Minimum Validation:
  - manually check the eight current topic directories against the ownership map
  - verify that no source item from `抽象规划.md` is left orphaned
- Module IO:
  - module_input_vars: `in_mother_sections(list)`, `in_existing_dirs(list)`
  - module_output_vars: `out_topic_map(table)`, `out_dependency_notes(list)`
  - io_mapping: source sections -> primary owner + dependency notes
  - io_boundary: planning docs only

## Task A2: Freeze Child-Directory Document Contract

- Goal: define the exact structure that every topic `01_*` and `02_*` document must follow.
- status: closed / wave15_verified
- depends_on: `["A1"]`
- blocks: `["A3","A4"]`
- Input:
  - this folder's coordination plan
  - the required `子目录文档写作要求`
  - existing high-quality sample documents
- Output:
  - one `01_*` section checklist
  - one `02_*` section checklist
  - one dependency rule for `01_* -> 02_*`
- Acceptance:
  - the `01_*` checklist includes goal, baseline, requirement clarification, scope/non-goals, recommended layering, order, serial/parallel, and minimum validation
  - the `02_*` checklist includes execution snapshot, serial/parallel rules, module boundaries, atomic task fields, and minimum validation
  - the contract is reusable across all active topics without topic-specific special cases
- Minimum Validation:
  - compare the checklist against at least one reference `01_*` and one reference `02_*`
  - verify that each required section is actionable rather than decorative
- Module IO:
  - module_input_vars: `in_sample_plan(doc)`, `in_sample_tasklist(doc)`, `in_required_rules(doc)`
  - module_output_vars: `out_plan_contract(checklist)`, `out_task_contract(checklist)`
  - io_mapping: repo rules + samples -> reusable contract
  - io_boundary: coordination docs only

## Task A3: Normalize Topic `01_*` Plan Documents

- Goal: rewrite each topic-level `01_*` file so it becomes a strong planning document rather than a loose note.
- status: closed / wave15_verified
- depends_on: `["A2"]`
- blocks: `["A4","A5"]`
- Input:
  - approved topic ownership map
  - per-topic repo anchors and existing notes
  - frozen `01_*` checklist
- Output:
  - one normalized `01_*` document per active topic directory
  - explicit topic-level scope and non-goals
  - explicit implementation order and dependency notes
- Acceptance:
  - each `01_*` contains all mandatory planning sections
  - baseline statements are either tied to repo anchors or clearly marked as validation gaps
  - topic boundaries do not conflict with the ownership map
  - recommended layering is concrete enough for a later task list to derive from it
- Minimum Validation:
  - spot-check headings for every active topic `01_*`
  - verify that each `01_*` includes at least one structure check and one flow check under minimum validation
- Module IO:
  - module_input_vars: `in_topic_map(table)`, `in_repo_anchors(list)`, `in_plan_contract(checklist)`
  - module_output_vars: `out_normalized_plan_doc(file)`, `out_scope_notes(list)`, `out_dependency_notes(list)`
  - io_mapping: topic ownership + repo anchors -> normalized plan doc
  - io_boundary: per-topic `01_*` docs only

## Task A4: Normalize Topic `02_*` Atomic Task Documents

- Goal: convert each topic plan into an executable atomic task list with stable dependency rules.
- status: closed / wave15_verified
- depends_on: `["A3"]`
- blocks: `["A5"]`
- Input:
  - normalized topic `01_*` documents
  - frozen `02_*` checklist
  - per-topic module boundaries and likely validation gates
- Output:
  - one normalized `02_*` document per active topic directory
  - atomic tasks with explicit dependencies, inputs, outputs, acceptance, and minimum validation
  - one per-topic serial/parallel rule set
- Acceptance:
  - each `02_*` starts with an execution status snapshot
  - each task is atomic enough to assign to one owner without reopening global scope
  - each task has inspectable output and a minimum credible validation step
  - serial/parallel rules are consistent with the corresponding `01_*`
- Minimum Validation:
  - spot-check that every task has `Goal/depends_on/Input/Output/Acceptance/Minimum Validation`
  - verify that no task depends on a topic boundary that the `01_*` document did not freeze
- Module IO:
  - module_input_vars: `in_plan_doc(file)`, `in_task_contract(checklist)`, `in_module_boundaries(obj)`
  - module_output_vars: `out_normalized_task_doc(file)`, `out_task_graph(graph)`, `out_validation_gates(list)`
  - io_mapping: normalized plan doc -> atomic task graph + task doc
  - io_boundary: per-topic `02_*` docs only

## Task A5: Cross-Topic Coverage and Dependency Review

- Goal: review all active topic directories together to ensure the split remains coherent.
- status: closed / wave15_verified
- depends_on: `["A3","A4"]`
- blocks: `["A6"]`
- Input:
  - normalized topic `01_*` and `02_*` documents
  - mother-document ownership map
- Output:
  - one coverage review note
  - one dependency drift list
  - one duplicate-scope list, if any
- Acceptance:
  - every major requirement in `抽象规划.md` maps to exactly one primary topic
  - shared concerns are recorded as dependencies instead of copied main plans
  - no topic `02_*` task graph contradicts the topic `01_*` scope
- Minimum Validation:
  - compare the topic set against the ownership map
  - check at least one shared boundary pair, such as `typed-knowledge-organization` vs `graph-editing-and-reporting`, for duplicated ownership
- Module IO:
  - module_input_vars: `in_topic_docs(list)`, `in_topic_map(table)`
  - module_output_vars: `out_coverage_report(doc)`, `out_drift_items(list)`, `out_duplicate_items(list)`
  - io_mapping: topic docs + ownership map -> coverage and drift report
  - io_boundary: planning docs only

## Task A6: External Index Sync Handoff

- Goal: prepare a clean closure note for upper-level index synchronization without performing those external edits in this work package.
- status: closed / wave15_verified
- depends_on: `["A5"]`
- blocks: `[]`
- Input:
  - list of normalized topic directories and files
  - coverage review result
  - repository index update rules
- Output:
  - one handoff note for index owners
  - exact path list that should be synchronized by the external index-maintenance step
- Acceptance:
  - the handoff lists the directories/files that need upstream index visibility
  - the handoff does not assume index work is already complete
  - no out-of-scope index file is edited as part of this task
- Minimum Validation:
  - verify that the handoff path list matches the normalized topic-directory set
  - confirm that directory-local normalization is complete before closure is requested
- Module IO:
  - module_input_vars: `in_normalized_docs(list)`, `in_index_rules(doc)`
  - module_output_vars: `out_external_handoff(note)`, `out_sync_paths(list)`
  - io_mapping: normalized docs + index rules -> external sync handoff
  - io_boundary: handoff documentation only

## Minimum Gate for This Work Package

- The coordination `01_*` document explains the split contract clearly enough to guide topic owners.
- The coordination `02_*` document expresses a repeatable execution method instead of a loose checklist.
- Directory-local planning work stays inside topic-planning documents.
- Any upper-level index work is explicitly marked as an external follow-up step.
