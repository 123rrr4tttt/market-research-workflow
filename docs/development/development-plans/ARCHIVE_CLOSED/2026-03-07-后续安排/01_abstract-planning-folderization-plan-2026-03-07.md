<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Abstract Planning Folderization Plan (2026-03-07)

> Date: 2026-03-07
> Scope: `development/latest-dev-docs/development-plans/CURRENT_DEV/*`
> Status: planning and normalization guide for topic-folder documentation

## 1. Goal

This document defines how `抽象规划.md` should be split, normalized, and handed off into topic-specific directories.

The immediate goal is not to finish every downstream design. The goal is to make the folder structure and starter documents executable enough that follow-up topic owners do not need to re-derive:

- what problem each topic owns;
- what the current repo baseline already gives them;
- what is in scope for the first pass;
- what can run in parallel versus what must stay serial;
- what minimum validation a topic document must already include.

## 2. Current Baseline

The current repository already provides the main inputs needed for folderization:

- `抽象规划.md` is the mother document for cross-topic demand sources, priority framing, and theme boundaries.
- `development/latest-dev-docs/README.md` already treats `development/latest-dev-docs` as the first-entry index and shows the `CURRENT_DEV` topic set.
- `CURRENT_DEV` already contains the expected March 7 topic directories for:
  - `writing-workbench-evolution`
  - `typed-knowledge-organization`
  - `graph-editing-and-reporting`
  - `ingest-digestion-and-long-cycle-automation`
  - `crawler-source-expansion`
  - `frontend-i18n-theme-modularization`
  - `llm-service-and-agent-platformization`
  - `dual-frontend-workbench-topology`

The quality gap is structural rather than thematic:

- the mother document is useful, but still too dense to be used as a direct execution plan;
- the split contract for child directories is described narratively, but not enforced as a stable document template;
- the atomic task list is too light to guide repeatable per-topic normalization work.

## 3. Requirement Clarification

### 3.1 Problem This Plan Solves

One abstract planning document should not remain the only place where future work is explained. Topic owners need a stable directory-level contract so that each theme can evolve independently without re-opening the same boundary debate.

### 3.2 Primary Consumers

- Main agent or maintainer responsible for creating or normalizing topic directories under `CURRENT_DEV`.
- Topic-level child agents responsible for rewriting the corresponding `01_*` and `02_*` documents.
- Reviewers who need to verify whether a topic directory is ready for deeper planning.

### 3.3 Core Writing Requirement for Child Directories

The section `子目录文档写作要求` in this folder is the minimum contract, not a suggestion.

Each child directory must make two things explicit:

1. `01_*` must clarify the problem, baseline, scope, recommended layering, order, dependency shape, and minimum validation.
2. `02_*` must convert that clarified plan into atomic execution units with status, dependencies, module boundaries, inputs, outputs, acceptance, and minimum checks.

### 3.4 Theme Ownership Rule

Each requirement from `抽象规划.md` must have exactly one primary topic owner.

- The primary owner writes the main solution path.
- Other affected topics only record dependency or interface impact.
- Cross-topic overlap is resolved by boundary notes, not by duplicating the same main plan in multiple directories.

## 4. Scope and Non-Goals

### 4.1 In Scope

- Freeze the topic grouping and naming convention.
- Define the canonical `01_*` and `02_*` starter-document contract.
- Describe the recommended execution order for creating or normalizing child topic directories.
- Define minimum structural and content-level validation for topic folders.

### 4.2 Non-Goals

- Writing the final implementation design for all eight topics inside this directory.
- Locking database models, API contracts, or UI details for each topic before topic-level exploration.
- Renaming existing directories or files unless naming/date rules are already broken.
- Treating index updates as part of the directory-local authoring work; index sync is a follow-up closure step owned outside this folder.

## 5. Recommended Folderization Model

The recommended model has four layers.

| Layer | Purpose | Required Artifact | Notes |
| --- | --- | --- | --- |
| Mother source | Keep cross-topic context and original demand source | `抽象规划.md` | Remains the single upstream requirement source for the theme set |
| Coordination | Freeze the split contract and execution method | `01_abstract-planning-folderization-plan-2026-03-07.md`, `02_atomic-tasklist-abstract-planning-folderization-2026-03-07.md` | This directory should explain *how* to split and normalize |
| Topic execution | Carry one theme per directory | `YYYY-MM-DD-topic-slug/` | One topic, one directory, one primary owner |
| Topic starter docs | Make each topic actionable | `01_<topic>-plan-YYYY-MM-DD.md`, `02_atomic-tasklist-<topic>-YYYY-MM-DD.md` | Mandatory starter pair for every active topic |

## 6. Recommended Topic Set

The current split should stay aligned with the eight themes already derived from the mother document.

| Topic | Focus | Boundary Reminder |
| --- | --- | --- |
| `writing-workbench-evolution` | Writing flow, templates, related materials, LLM-assisted writing | Do not absorb platform-wide LLM orchestration |
| `typed-knowledge-organization` | Type nodes, classification, collections, thematic grouping | Do not absorb graph editing as the main solution |
| `graph-editing-and-reporting` | Editable graph workflow, sync, report handoff | Do not redefine the full knowledge model here |
| `ingest-digestion-and-long-cycle-automation` | Long text/PDF digestion and long-cycle tasks | Do not absorb source-expansion planning |
| `crawler-source-expansion` | Source coverage, crawler adapters, source quality | Do not replace downstream ingest design |
| `frontend-i18n-theme-modularization` | i18n, theme, frontend modularity baseline | Do not merge with full workbench topology design |
| `llm-service-and-agent-platformization` | Model routing, agent platform, long-lived orchestration | Do not swallow writing-workbench UX scope |
| `dual-frontend-workbench-topology` | Modern workbench layering by interaction intensity | Do not reopen legacy frontend as an active baseline |

If a future split is required, the default rule is: preserve the current primary topic set first, then split only the overloaded topic instead of reshuffling all boundaries.

## 7. Child Directory Documentation Standard

### 7.1 `01_*` Plan Contract

Every topic-level `01_*` document should contain, at minimum:

- Goal
- Current baseline
- Requirement clarification
- Scope and non-goals
- Recommended solution or layered breakdown
- Implementation order
- Serial/parallel relationship
- Minimum validation

The content standard is:

- baseline must cite repo anchors or clearly mark an item as a gap to verify;
- requirement clarification must distinguish user/system needs from guessed implementation;
- scope must include both what is being solved now and what is intentionally deferred;
- recommended layering must make module ownership or dependency direction explicit;
- minimum validation must include at least one structure check and one flow check.

### 7.2 `02_*` Atomic Task Contract

Every topic-level `02_*` document should contain, at minimum:

- Execution status snapshot
- Global serial/parallel rules
- Module boundary or IO contract
- Atomic tasks with:
  - goal
  - dependency
  - input
  - output
  - acceptance
  - minimum validation

The content standard is:

- tasks must be atomic enough that a child agent can own one task without redefining the whole topic;
- dependencies must be concrete, not “do later” placeholders;
- output must be inspectable;
- minimum validation must be the smallest credible gate for that task, not a generic “self-check”.

## 8. Recommended Implementation Order

1. Freeze the mapping from mother-document requirements to the eight topic owners.
2. Freeze the directory-level document contract before any topic-specific rewriting begins.
3. Reuse existing topic directories when names already match the naming/date rule; only create missing ones.
4. Normalize each topic `01_*` plan document first.
5. Normalize each topic `02_*` atomic task document after the corresponding `01_*` scope is stable.
6. Run directory-local structural and dependency validation.
7. Hand off upper-level index synchronization as a separate closure step.

This keeps planning quality ahead of indexing work. Indexes should point to normalized topic documents, not to half-formed placeholders.

## 9. Serial and Parallel Relationship

The work should follow this dependency model:

- Serial:
  - freeze source-to-topic mapping before any topic rewrite;
  - freeze the child-document contract before parallel topic work;
  - inside one topic directory, complete `01_*` before finalizing `02_*`;
  - perform cross-topic review before external index sync.
- Parallel:
  - once the document contract is frozen, different topic directories can be normalized in parallel;
  - baseline gathering and topic-specific repo anchor checks can run independently per topic;
  - a single topic directory may proceed independently as long as it does not redefine another topic's primary ownership.

Conflict rule:

- Do not let multiple editors rewrite the same topic file concurrently.
- Do not mix directory-local topic normalization with upper-level index editing in the same work package.

## 10. Minimum Validation

The split is minimally acceptable only when all of the following are true:

- Structural validation
  - each active topic has one directory;
  - each active topic directory has one `01_*` and one `02_*` starter document;
  - file names and dates follow repository naming rules.
- Content validation
  - each `01_*` contains the required planning sections;
  - each `02_*` contains the required task sections and dependency shape;
  - no topic document silently replaces another topic's ownership boundary.
- Cross-topic validation
  - every major requirement from `抽象规划.md` maps to exactly one primary topic;
  - shared concerns are recorded as dependencies instead of duplicate main plans.
- Closure validation
  - directory-local work is complete before external index sync is requested;
  - any remaining index work is explicitly handed off rather than assumed done.

## 11. Deliverable Definition

When this plan is executed correctly, the result should be:

- one stable mother document for cross-topic demand input;
- one coordination directory explaining split method and normalization rules;
- one normalized starter pair (`01/02`) per active topic directory;
- one clear handoff point for external index synchronization.
