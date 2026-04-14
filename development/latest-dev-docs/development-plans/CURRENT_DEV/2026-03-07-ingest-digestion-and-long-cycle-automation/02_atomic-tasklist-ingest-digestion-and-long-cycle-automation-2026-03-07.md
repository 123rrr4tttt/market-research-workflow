# Atomic Task List: Ingest Digestion and Long-Cycle Automation (2026-03-07)

## Execution Status Snapshot

- `A1`: pending, freeze repo-grounded baseline and remove outdated assumptions.
- `A2`: pending, define unified input taxonomy and digestion-stage contract.
- `A3`: pending, define derived-artifact identity and lineage rules.
- `A4`: pending, freeze time-semantics reuse rules around density and window selection.
- `A5`: pending, define the minimum long-cycle task object and template-instance boundary.
- `A6`: pending, map digestion outputs to downstream consumers and identify reusable vs transient artifacts.
- `A7`: pending, assemble minimum validation scenarios and repo checks.
- `A8`: pending, close wording drift between the main plan and this task list.

## Global Serial-Parallel Rules

- `L0` serial bootstrap: `A1` must complete first.
- `L1` parallel contract drafting after `A1`:
  - `A2` unified digestion contract
  - `A4` time-semantics reuse contract
- `L2` conditional follow-up:
  - `A3` depends on `A2`
  - `A5` depends on `A2` and `A4`
- `L3` downstream convergence:
  - `A6` depends on `A2` and `A3`
  - `A7` depends on `A3`, `A5`, and `A6`
- `L4` serial closure: `A8` runs after `A1-A7`.
- File-conflict rule:
  - tasks editing `01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md` must run serially by task id;
  - tasks editing `02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md` must run serially by task id.

## Global Module Boundaries

- Intake boundary:
  - read `main/backend/app/api/ingest.py`
  - read `main/backend/app/services/ingest/*`
  - read `main/backend/app/services/resource_pool/extract.py`
- Time boundary:
  - read `main/backend/app/services/tasks.py`
  - read `main/backend/app/api/stats.py`
  - read `main/backend/app/services/stats/prompt_time_density.py`
- Downstream boundary:
  - read `main/backend/app/api/resource_pool.py`
  - read `main/backend/app/api/llm_report.py`
  - read `main/backend/app/api/writing.py`
  - read related writing/report services only as needed
- Write boundary:
  - write only the two markdown files in this directory

## Global Documentation Rules

- Prefer English for the main body; short Chinese notes are acceptable only when they remove ambiguity.
- Reuse verified repo paths and current terminology instead of inventing new subsystem names.
- When the repo already has a capability, record it as baseline and shift the gap description to missing contract, missing boundary, or missing orchestration.
- Do not claim a new table, API, or scheduler exists unless it is verified in repo.

## Task A1: Repo Baseline Evidence Snapshot

- Goal: capture the current ingest, time, and downstream surfaces so the plan does not repeat stale assumptions.
- status: pending
- depends_on: `[]`
- blocks: `["A2","A4","A6"]`
- Input:
  - current `01` and `02` docs
  - `main/backend/app/services/tasks.py`
  - `main/backend/app/api/ingest.py`
  - `main/backend/app/api/resource_pool.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/writing.py`
- Output:
  - one repo-grounded baseline summary
  - one verified gap list
  - one list of reusable surfaces
- Acceptance:
  - records at least one verified file per major surface: ingest, time, downstream
  - does not describe existing writing/report APIs as absent
  - distinguishes "implemented capability" from "missing cross-cutting contract"
- Minimum verification:
  - `rg -n "prefix=\"/writing\"|prefix=\"/llm-report\"|prefix=\"/resource_pool\"" main/backend/app/api`
  - `rg -n "task_select_prompt_time_windows|task_ingest_single_url|task_raw_import_documents" main/backend/app/services/tasks.py`
- Module IO:
  - `module_input_vars`: `in_current_docs(files)`, `in_repo_surfaces(list)`
  - `module_output_vars`: `out_baseline(doc)`, `out_gap_list(list)`, `out_reuse_map(list)`
  - `io_mapping`: verified repo surfaces -> baseline facts + gap framing
  - `io_boundary`: docs in target directory only

## Task A2: Unified Input Taxonomy and Digestion Stages

- Goal: classify input families and freeze the minimum digestion decision chain.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A3","A5","A6"]`
- Input:
  - ingest entrypoints and extraction utilities
  - evidence from `A1`
- Output:
  - one input taxonomy
  - one digestion-stage contract
  - one rule set for when chunking is mandatory, optional, or skipped
- Acceptance:
  - classifies at least URL-driven inputs, raw imports, report-shaped inputs, and derived markdown/report artifacts
  - states a common chain such as normalization -> decision -> optional chunking -> summary/extraction -> structured package
  - does not imply every input already uses the same implementation path today
- Minimum verification:
  - `rg -n "single_url|raw_import|structured_extraction|url_pool" main/backend/app/services/ingest`
  - `rg -n "segment_text|RecursiveCharacterTextSplitter|chunk" main/backend/app/services/extraction/topic_workflow.py main/backend/app/services/indexer/policy.py`
- Module IO:
  - `module_input_vars`: `in_entrypoints(list)`, `in_chunk_helpers(list)`, `in_current_gaps(list)`
  - `module_output_vars`: `out_taxonomy(table)`, `out_stage_contract(doc)`, `out_chunk_rules(list)`
  - `io_mapping`: intake evidence -> normalized taxonomy + digestion stages
  - `io_boundary`: docs in target directory only

## Task A3: Derived Artifact Identity and Lineage Rules

- Goal: define how LLM-generated reports and writing-domain markdown are treated when they re-enter digestion.
- status: pending
- depends_on: `["A2"]`
- blocks: `["A6","A7"]`
- Input:
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/services/writing/document_service.py`
  - `main/backend/app/models/writing_entities.py`
- Output:
  - one derived-artifact classification section
  - one lineage rule set
  - one rule for re-digestion eligibility
- Acceptance:
  - distinguishes original source material from derived artifacts
  - preserves conceptual parent/source context and processing time
  - states whether re-digestion is allowed, conditional, or disallowed for each artifact family
- Minimum verification:
  - `rg -n "body_md|draft_body_md|citation|source_type" main/backend/app/api/writing.py main/backend/app/services/writing main/backend/app/contracts/schemas/writing.py main/backend/app/models/writing_entities.py`
  - `rg -n "render_markdown|resolve_report_sources|report" main/backend/app/api/llm_report.py main/backend/app/services/llm_report_generator.py main/backend/app/services/llm_report_source_enrichment.py`
- Module IO:
  - `module_input_vars`: `in_artifact_surfaces(list)`, `in_taxonomy(table)`
  - `module_output_vars`: `out_identity_rules(doc)`, `out_lineage_rules(list)`, `out_redigestion_policy(list)`
  - `io_mapping`: downstream artifact evidence -> intake identity + lineage rules
  - `io_boundary`: docs in target directory only

## Task A4: Time-Semantics Reuse Contract

- Goal: document how time density and window selection participate in long-cycle ingest planning.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A5","A7"]`
- Input:
  - `main/backend/app/api/stats.py`
  - `main/backend/app/services/stats/prompt_time_density.py`
  - `main/backend/app/services/tasks.py`
  - existing time-remediation documents
- Output:
  - one time-field glossary
  - one rule set for source time vs processed time vs task window time
  - one description of how `prompt_time_density` informs task selection
- Acceptance:
  - keeps time-window selection as a reused capability, not a replacement candidate
  - separates at least three concepts: source time, processing time, task window time
  - records whether density is used for selection, prioritization, or gap-fill scenarios
- Minimum verification:
  - `rg -n "prompt_time_density|select_prompt_time_windows" main/backend/app/api/stats.py main/backend/app/services/stats/prompt_time_density.py main/backend/app/services/tasks.py`
- Module IO:
  - `module_input_vars`: `in_time_surfaces(list)`, `in_task_inventory(file)`, `in_existing_time_docs(dir)`
  - `module_output_vars`: `out_time_glossary(table)`, `out_window_rules(list)`, `out_density_reuse(doc)`
  - `io_mapping`: verified time surfaces -> reuse contract
  - `io_boundary`: docs in target directory only

## Task A5: Long-Cycle Task Object and Template Boundary

- Goal: define the minimum planning object for repeated ingest work without promising a full scheduler implementation.
- status: pending
- depends_on: `["A2","A4"]`
- blocks: `["A7"]`
- Input:
  - digestion contract from `A2`
  - time reuse contract from `A4`
  - current task inventory from `main/backend/app/services/tasks.py`
- Output:
  - one minimal long-cycle task object definition
  - one template-vs-instance boundary
  - one lifecycle status outline
- Acceptance:
  - includes goal, input selector, window strategy, cadence, output target, and status snapshot
  - distinguishes reusable task template data from run-specific parameters
  - does not imply an existing recurring scheduler table or service
- Minimum verification:
  - `rg -n "task_collect_|task_ingest_|task_raw_import|task_extract_resource_pool|task_select_prompt_time_windows" main/backend/app/services/tasks.py`
  - `sed -n '1,120p' main/backend/app/contracts/tasks.py`
- Module IO:
  - `module_input_vars`: `in_digestion_contract(doc)`, `in_time_contract(doc)`, `in_task_inventory(file)`
  - `module_output_vars`: `out_long_cycle_spec(doc)`, `out_template_boundary(list)`, `out_status_model(list)`
  - `io_mapping`: digestion + time constraints -> long-cycle planning object
  - `io_boundary`: docs in target directory only

## Task A6: Downstream Handoff Matrix

- Goal: map digestion outputs to actual downstream consumers and separate durable outputs from transient process artifacts.
- status: pending
- depends_on: `["A2","A3"]`
- blocks: `["A7"]`
- Input:
  - digestion contract from `A2`
  - derived artifact rules from `A3`
  - downstream API/service surfaces
- Output:
  - one handoff matrix
  - one list of reusable persisted outputs
  - one list of transient processing-only artifacts
- Acceptance:
  - covers at least resource pool, report generation, writing-related consumers, and contract-level knowledge/graph handoff
  - states what downstream receives: raw content, chunked content, structured extract, summary, or evidence bundle
  - avoids inventing downstream schemas that are not yet verified
- Minimum verification:
  - `rg -n "prefix=\"/resource_pool\"|prefix=\"/llm-report\"|prefix=\"/writing\"" main/backend/app/api`
  - `rg -n "aggregate_cards|list_documents|resolve_report_sources|unified_search" main/backend/app/services`
- Module IO:
  - `module_input_vars`: `in_output_contract(doc)`, `in_artifact_rules(doc)`, `in_downstream_surfaces(list)`
  - `module_output_vars`: `out_handoff_matrix(table)`, `out_reusable_outputs(list)`, `out_transient_outputs(list)`
  - `io_mapping`: digestion outputs -> downstream-specific handoff map
  - `io_boundary`: docs in target directory only

## Task A7: Minimal Validation Scenarios

- Goal: produce the smallest validation set that future implementation work can execute against.
- status: pending
- depends_on: `["A3","A5","A6"]`
- blocks: `["A8"]`
- Input:
  - all previous task outputs
- Output:
  - one structural validation checklist
  - one external-input scenario
  - one derived-artifact scenario
  - one window-driven long-cycle scenario
- Acceptance:
  - includes at least one structural check and at least two flow checks
  - references real repo paths or commands for evidence
  - is small enough to run as a minimum regression gate, not a full QA program
- Minimum verification:
  - review the final docs for consistent terms: `digestion`, `derived artifact`, `window strategy`, `handoff`
  - ensure every scenario names the input, the processing path, and the expected downstream target
- Module IO:
  - `module_input_vars`: `in_contracts(list)`, `in_handoff_matrix(table)`
  - `module_output_vars`: `out_validation_checklist(list)`, `out_scenarios(list)`
  - `io_mapping`: finalized contracts -> minimum validation set
  - `io_boundary`: docs in target directory only

## Task A8: Document Closure and Consistency Pass

- Goal: make the main plan and atomic task list read as one consistent execution package.
- status: pending
- depends_on: `["A1","A2","A3","A4","A5","A6","A7"]`
- blocks: `[]`
- Input:
  - revised `01` and `02` documents
- Output:
  - one terminology-consistent documentation set
  - one final wording cleanup pass
- Acceptance:
  - `01` contains goals, baseline, requirement clarification, scope/non-goals, layering, order, parallelism, and minimal validation
  - `02` contains execution snapshot, serial-parallel rules, boundaries, per-task goal/dependency/input/output/acceptance/minimum verification
  - no numbering drift or contradictory wording remains
- Minimum verification:
  - `git diff --check -- development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-ingest-digestion-and-long-cycle-automation/01_ingest-digestion-and-long-cycle-automation-plan-2026-03-07.md development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-ingest-digestion-and-long-cycle-automation/02_atomic-tasklist-ingest-digestion-and-long-cycle-automation-2026-03-07.md`
- Module IO:
  - `module_input_vars`: `in_main_plan(file)`, `in_atomic_tasks(file)`
  - `module_output_vars`: `out_consistent_docs(bool)`, `out_cleanup_notes(list)`
  - `io_mapping`: revised docs -> final consistent package
  - `io_boundary`: docs in target directory only
