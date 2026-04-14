# Ingest Digestion and Long-Cycle Automation Plan (2026-03-07)

> Date: 2026-03-07
> Scope: ingest digestion contract, derived artifact intake, long-cycle task semantics, time-window reuse, downstream handoff
> Status: planning document; this revision only improves documentation quality and does not claim new implementation facts

## 1. Goals

This topic should freeze a repo-aligned phase-1 plan for turning ingest from a set of intake entrypoints into a reusable digestion layer.

The minimum goals are:

1. Define one common digestion path for long text, PDF-like report content, and other document-shaped inputs.
2. Clarify how derived artifacts such as LLM-generated reports and writing-domain markdown may re-enter the platform without losing lineage.
3. Define the minimum long-cycle task semantics needed for repeated ingest planning without pretending a full scheduler already exists.
4. Reuse the existing time-density and time-window surfaces instead of creating a parallel time model.
5. Make downstream handoff explicit for resource pool, knowledge organization, graph/report generation, and writing-related consumers.

## 2. Current Baseline

### 2.1 Existing intake and extraction surfaces

The repo already has multiple ingest entrypoints and related extraction utilities:

- `main/backend/app/api/ingest.py`
- `main/backend/app/services/ingest/single_url.py`
- `main/backend/app/services/ingest/raw_import.py`
- `main/backend/app/services/ingest/url_pool.py`
- `main/backend/app/services/ingest/structured_extraction.py`
- `main/backend/app/services/ingest/reports/general.py`
- `main/backend/app/services/ingest/reports/california.py`
- `main/backend/app/services/resource_pool/extract.py`
- `main/backend/app/services/ingest/meaningful_gate.py`

This means the platform already knows how to collect, import, and extract. The gap is not "ingest does not exist"; the gap is that the repo does not yet present one clearly frozen digestion contract across these entrypoints.

### 2.2 Partial digestion primitives already exist

There are also reusable chunking or digestion-adjacent primitives outside the ingest folder:

- `main/backend/app/services/extraction/topic_workflow.py`
- `main/backend/app/services/indexer/policy.py`
- `main/backend/app/services/search/hybrid.py`

These files show that splitting, chunk selection, and structured extraction patterns already exist in the repo. What is missing is a documented rule for when ingest should reuse those patterns, when it should bypass them, and what normalized output shape downstream code should expect.

### 2.3 Task and time semantics already exist

Task execution and time-window selection are also not greenfield:

- `main/backend/app/services/tasks.py`
- `main/backend/app/api/stats.py`
- `main/backend/app/services/stats/prompt_time_density.py`
- `main/backend/app/contracts/tasks.py`

Concrete evidence in `tasks.py` includes:

- `task_ingest_single_url`
- `task_raw_import_documents`
- `task_extract_resource_pool_from_documents`
- `task_extract_resource_pool_from_tasks`
- `task_collect_weekly_reports`
- `task_collect_monthly_reports`
- `task_select_prompt_time_windows`

The repo therefore already has discrete tasks plus time-window selection. What is not yet frozen is a first-class long-cycle task definition with stable fields such as goal, input scope, cadence, selected window, output target, and lifecycle status.

### 2.4 Downstream consumers already exist

Several downstream consumers are already present and should be treated as reuse targets rather than future placeholders:

- Resource pool and extraction surfaces:
  - `main/backend/app/api/resource_pool.py`
  - `main/backend/app/services/resource_pool/unified_search.py`
- Report generation surfaces:
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
- Writing-domain surfaces:
  - `main/backend/app/api/writing.py`
  - `main/backend/app/services/writing/document_service.py`
  - `main/backend/app/services/writing/keyword_card_service.py`

This is important for the plan: writing/report/keyword-card consumers already exist, but the ingest-side re-entry and handoff rules are not yet frozen as one coherent contract.

### 2.5 Baseline gaps that this plan must close

The current repo shape still leaves these planning gaps:

- No repo-level taxonomy that clearly separates raw external inputs from derived artifacts.
- No documented decision rule for "pass through", "chunk first", "summarize first", or "extract first".
- No explicit lineage contract for derived artifacts re-entering ingestion.
- No first-class long-cycle task object visible from the current task inventory.
- No single validation matrix connecting ingest, time-window selection, and downstream handoff.

## 3. Requirement Clarification

### 3.1 Primary users and decision owners

This document is mainly for:

- backend owners aligning ingest, extraction, and task orchestration;
- downstream owners of knowledge organization, graph/report generation, and writing flows;
- future implementation agents that need a stable planning boundary before touching code.

### 3.2 Input classes that must be classified in phase 1

Phase 1 should classify at least the following input families:

- external URL-driven content from `single_url`, `url_pool`, and report collectors;
- raw imported text or files from `raw_import`;
- long text and report-shaped content that is likely to require chunking before structured extraction;
- derived artifacts from:
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/writing.py`

This plan can recommend classifications, but it must not invent unsupported implementation details such as existing database fields that have not been verified.

### 3.3 Questions that must be answered

The phase-1 document set must answer these questions clearly:

1. Which inputs are normalized into the same digestion path, and which stay on specialized paths?
2. Which inputs require chunking before extraction, and which can go directly to extraction or indexing?
3. How are derived artifacts distinguished from original source material?
4. Which lineage fields must be preserved conceptually, even if storage work is deferred?
5. How should time window, processed time, and original source time be kept distinct?
6. What is the minimum long-cycle task object that implementation work can build on later?
7. Which digestion outputs are reusable downstream assets, and which are transient processing artifacts?

## 4. Scope and Non-Goals

### 4.1 In scope

This topic currently includes:

- one unified digestion contract for long text, PDF-like reports, and similar document-shaped inputs;
- derived artifact intake rules for LLM reports and writing-domain markdown;
- minimum long-cycle task semantics built on top of existing task and time-window surfaces;
- reuse rules for `prompt_time_density` and task-side window selection;
- downstream handoff boundaries toward resource pool, knowledge organization, graph/report generation, and writing consumers.

### 4.2 Non-goals

This topic does not currently include:

- rewriting crawler-source expansion logic;
- replacing the current task runner with a new scheduler platform;
- freezing the complete knowledge graph schema;
- committing to new tables or migrations before implementation review;
- solving every historical ingest inconsistency in one document.

## 5. Recommended Layering

### 5.1 Layer A: Intake normalization

Responsibility:

- accept data from current ingest entrypoints;
- normalize the minimum metadata needed for digestion decisions;
- avoid coupling downstream stages to entrypoint-specific payload shape.

Recommended minimum normalized fields to freeze at documentation level:

- `project_key`
- `input_kind`
- `source_locator`
- `content_format`
- `source_time`
- `processed_time`
- `lineage_ref`
- `requested_downstream_targets`

These are recommended planning fields, not a claim that identical code-level fields already exist everywhere.

### 5.2 Layer B: Digestion decision and processing contract

Responsibility:

- decide whether a payload should pass through, be chunked, be summarized, or be structurally extracted first;
- reuse existing chunking and extraction helpers where possible;
- produce one documented output package for downstream handoff.

Recommended phase-1 digestion chain:

`normalized input -> digestion decision -> optional chunking -> summary/extraction -> structured result package -> downstream handoff`

The document should explicitly state:

- which input classes must go through chunking first;
- which inputs may bypass chunking;
- which outputs are mandatory before handoff;
- which diagnostics should be preserved for later audit.

### 5.3 Layer C: Derived artifact intake and lineage

Responsibility:

- define when generated or user-authored content becomes a digestible platform object;
- preserve conceptual lineage to upstream source or generation context;
- state whether re-digestion is allowed, optional, or prohibited by artifact type.

For phase 1, the document should freeze at least these conceptual rules:

- derived artifacts must remain distinguishable from raw external sources;
- lineage should record parent object or source context when available;
- time semantics should distinguish source-time from generation-time and processing-time;
- downstream consumers must know whether they received an original source, a derived artifact, or a mixed evidence package.

### 5.4 Layer D: Long-cycle orchestration semantics

Responsibility:

- define a planning object for repeated ingest work;
- reuse current task execution and time-window selection surfaces;
- stop short of promising a full scheduler rewrite.

Recommended minimum long-cycle task fields to freeze in docs:

- `task_goal`
- `input_selector`
- `window_strategy`
- `cadence`
- `priority_rule`
- `output_target`
- `success_status`
- `failure_status`
- `last_run_snapshot`

This section should explicitly separate:

- task template semantics;
- per-run instance parameters;
- window selection inputs and outputs.

### 5.5 Layer E: Downstream handoff

Responsibility:

- map digestion outputs to concrete consumers already present in repo;
- distinguish persistent reusable outputs from transient process artifacts;
- make reuse boundaries explicit so later implementation does not invent parallel data shapes.

Phase-1 handoff targets should at least cover:

- resource pool style search/index consumers;
- knowledge-organization and graph-facing consumers at contract level;
- report generation and writing-related consumers that already exist in backend APIs.

## 6. Recommended Implementation Order

The safest order is:

1. Freeze a baseline evidence snapshot from current repo surfaces.
2. Freeze the unified input taxonomy and digestion-stage contract.
3. Freeze derived artifact identity and lineage rules.
4. Freeze time-semantics reuse rules around `prompt_time_density` and task window selection.
5. Freeze the minimum long-cycle task object and task-template boundary.
6. Freeze the downstream handoff matrix.
7. Freeze the minimal validation scenarios and consistency checks.

This order avoids the common failure mode where task automation is designed before the digestion contract and time semantics are stable.

## 7. Parallel and Serial Relationships

Recommended planning dependency chain:

- Serial bootstrap:
  - baseline evidence snapshot must happen first.
- First parallel slice after bootstrap:
  - unified digestion contract review;
  - time-semantics reuse review.
- Conditional parallel slice:
  - derived artifact rules may proceed once input taxonomy is stable;
  - downstream handoff review may proceed once digestion output shape is stable enough.
- Serial convergence:
  - long-cycle task definition must wait for both digestion and time-semantics decisions.
- Final closure:
  - validation matrix and wording cleanup should run only after all previous contracts are stable.

This keeps low-coupling work parallel and forces convergent decisions back into serial checkpoints.

## 8. Minimal Validation

The minimum validation for this planning theme should cover structure, process, and repo evidence.

### 8.1 Structural validation

The document set should prove that it contains:

- one stable input taxonomy;
- one digestion-stage contract;
- one derived-artifact lineage rule set;
- one long-cycle task object definition;
- one downstream handoff matrix;
- one validation section that references real repo surfaces.

### 8.2 Repo evidence checks

The following commands are sufficient for a minimum repo-grounding pass:

```bash
rg -n "task_ingest_single_url|task_raw_import_documents|task_extract_resource_pool_from_documents|task_extract_resource_pool_from_tasks|task_collect_weekly_reports|task_collect_monthly_reports|task_select_prompt_time_windows" main/backend/app/services/tasks.py

rg -n "prompt_time_density|select_prompt_time_windows" main/backend/app/api/stats.py main/backend/app/services/stats/prompt_time_density.py main/backend/app/services/tasks.py

rg -n "prefix=\"/resource_pool\"|prefix=\"/llm-report\"|prefix=\"/writing\"" main/backend/app/api

rg -n "segment_text|chunk|RecursiveCharacterTextSplitter" main/backend/app/services/extraction/topic_workflow.py main/backend/app/services/indexer/policy.py
```

### 8.3 Flow validation scenarios

At least three scenario checks should be documented:

1. External document path:
   `raw import or report collector -> digestion decision -> structured package -> resource pool or knowledge-facing handoff`
2. Derived artifact re-entry path:
   `llm report or writing markdown -> lineage-preserved digestion intake -> reusable evidence or writing/report consumer`
3. Window-driven long-cycle path:
   `candidate windows -> prompt_time_density selection -> long-cycle task run -> output target + status snapshot`

## 9. Open Risks and Pending Decisions

The document should carry these risks forward explicitly:

- PDF-specific parsing may need a specialized branch even if the high-level digestion contract is shared.
- Derived artifact lineage may require storage work later; this document should freeze contract language first, not promise migrations.
- Long-cycle cadence and execution state may outgrow the current task helper surfaces; that should be recorded as a future implementation risk, not solved by assumption here.
- Downstream knowledge/graph consumers may need more precise object contracts than phase 1 can responsibly freeze.
