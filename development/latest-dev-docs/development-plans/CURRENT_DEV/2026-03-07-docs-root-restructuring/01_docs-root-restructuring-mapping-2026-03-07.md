# Docs Root Restructuring Plan and Mapping

> Date: 2026-03-07
> Scope: `development/latest-dev-docs`, existing `docs/`, and repo references that currently point to the development-doc snapshot
> Status: planning only; this document defines migration intent and sequencing, not a file-move commit

## 1. Goal

Define a safe restructuring plan for developer-facing documentation so that:

1. the repo stops relying on `development/latest-dev-docs` as the only long-term container for mixed planning, implementation, architecture, and governance material;
2. future moves can be executed in batches with clear destination rules;
3. link churn, duplicate copies, and index breakage are controlled during the transition.

This document is intentionally limited to planning, classification rules, and migration order. It does not claim that the migration has already happened.

## 2. Current Baseline

The current repo state already exposes two documentation roots with different roles:

- `development/latest-dev-docs` is the current developer-doc snapshot and is explicitly described in repo guidance as the important index and first entry.
- `docs/` already exists and already hosts stable topic areas such as `ai`, `data-catalog`, `data-contracts`, `implementation`, `ops`, `reference-pool`, and `security`.

Inside `development/latest-dev-docs`, the current top-level structure is already theme-oriented but semantically mixed:

- `root-plans`
- `backend-core`
- `backend-docs`
- `ops-frontend`
- `development-plans`
- `frontend-modern`

Inside those trees, the same directory family appears repeatedly:

- `A_ARCHITECTURE`
- `B_API`
- `C_INGEST`
- `D_TEST`
- `E_OPS`
- `F_PLAN`
- `G_REVIEW`
- `main/`

There is also clear path coupling in the repo today. Existing references to `development/latest-dev-docs` are present in at least these places:

- root `README.md`
- `codex_settings/AGENTS.md`
- `scripts/docs_only_workflow.sh`
- multiple development docs and review documents under `development/latest-dev-docs`

This means the migration problem is not just “rename one folder”. The real problem is that:

- `development/latest-dev-docs` is simultaneously a live entrypoint, a snapshot area, and a mixed semantic archive;
- `docs/` already contains production-facing and reference-facing material, but not yet the full target taxonomy needed for process docs;
- many links, scripts, and habits still assume the old root.

## 3. Problem Layers

### 3.1 Root Ambiguity

The repo currently has both `development/latest-dev-docs` and `docs/`, but their responsibilities are not cleanly separated. Readers can reach valid documentation from both places, which makes ownership and future indexing unclear.

### 3.2 Semantic Mixing

Many directories mix:

- planning artifacts,
- implementation evidence,
- architecture notes,
- governance/review material,
- merged snapshot documents.

This is the main reason a direct folder rename would be unsafe. A large portion of the tree needs classification before relocation.

### 3.3 Reference Coupling

Paths to `development/latest-dev-docs` are hard-coded in documentation and scripts. Moving files before fixing these references would create broken navigation and brittle automation.

### 3.4 Migration Safety

Because `development/latest-dev-docs/README.md` is still the declared first entry, any migration must keep a compatibility layer until new indexes, scripts, and reader habits are stable.

## 4. Scope and Non-Goals

### 4.1 In Scope

- define the target classification model;
- define root-level and subdirectory-level mapping rules;
- define a staged migration order;
- define the minimum validation set;
- define rollback expectations.

### 4.2 Out of Scope for This Document

- moving files in this task;
- editing repo indexes in this task;
- rewriting every mixed document into a new semantic form;
- deciding the final information architecture for unrelated existing `docs/ai`, `docs/security`, `docs/data-catalog`, or `docs/data-contracts`.

## 5. Migration Principles

1. Preserve entry stability before optimizing structure.
2. Classify by document role first, then move paths.
3. Prefer file-level routing when directory-level semantics are mixed.
4. Move low-ambiguity material first and mixed archives later.
5. Keep `development/latest-dev-docs` readable as a compatibility entry until the new navigation has been proven.
6. Do not create duplicate “authoritative copies” without an explicit deprecation path.
7. Validate index integrity and path references after every migration batch.

## 6. Recommended Target Model

The repo already has a usable `docs/implementation` root. For the missing semantic buckets, the recommended destination family is:

```text
docs/
  development/
  implementation/
  architecture/
  governance/
```

This recommendation is intentionally narrow:

- keep existing unrelated roots such as `docs/ai`, `docs/ops`, `docs/security`, `docs/data-catalog`, and `docs/data-contracts` unchanged in this migration;
- add the missing roots only to absorb material currently trapped in `development/latest-dev-docs`;
- treat `docs/implementation` as an existing stable destination, not a new invention.

Role definitions:

- `docs/development/`: active plans, execution boards, design briefs, atomic tasklists, stage-specific reviews, historical development archives.
- `docs/implementation/`: adopted workflows, stable API/interface notes, test baselines, runbooks, accepted delivery evidence.
- `docs/architecture/`: system structure, long-lived constraints, cross-cutting design decisions, target-state topology.
- `docs/governance/`: release policy, review conclusions, reliability baselines, operational governance rules.

## 7. Mapping Rules

### 7.1 Root-Level Mapping

| Current path | Current role | Recommended destination | Notes |
|---|---|---|---|
| `development/latest-dev-docs/development-plans` | active planning and execution closure | primarily `docs/development/development-plans` | split out architecture / implementation / governance files when semantics are explicit |
| `development/latest-dev-docs/root-plans` | top-level planning, evidence, and review mix | file-level split across all four roots | do not move as one package |
| `development/latest-dev-docs/backend-core` | implementation notes mixed with architecture and review | primarily `docs/implementation/backend-core` | route `A_ARCHITECTURE` and governance-like ops baselines separately |
| `development/latest-dev-docs/backend-docs` | backend delivery docs mixed with stage artifacts | primarily `docs/implementation/backend-docs` | keep planning/review artifacts in `docs/development` or `docs/governance` |
| `development/latest-dev-docs/ops-frontend` | frontend implementation, plan, review, and ops mix | split between `docs/implementation`, `docs/development`, `docs/architecture`, `docs/governance` | `main/` requires file-level review |
| `development/latest-dev-docs/frontend-modern` | design-input and prototype-style material | `docs/development/frontend-modern` by default | only promote to implementation if the repo later treats it as stable product guidance |

### 7.2 Shared Subdirectory Rules

These rules apply across subprojects unless the folder content is obviously mixed at file level:

| Subdirectory | Default destination |
|---|---|
| `A_ARCHITECTURE` | `docs/architecture/...` |
| `B_API` | usually `docs/implementation/...`; keep planning-style API design notes in `docs/development/...` |
| `C_INGEST` | `docs/implementation/...` when it records an adopted flow; otherwise `docs/development/...` |
| `D_TEST` | `docs/implementation/...` for stable test baselines; `docs/development/...` for task-stage validation notes |
| `E_OPS` | `docs/implementation/...` for runbooks; `docs/governance/...` for reliability or policy baselines |
| `F_PLAN` | `docs/development/...` |
| `G_REVIEW` | `docs/governance/...` when it closes with policy or release judgment; otherwise `docs/development/...` |
| `main/` | classify per file, never move blindly as a whole directory |

### 7.3 Project-Specific Routing Notes

#### `development-plans`

- keep `CURRENT_DEV/` under the development-classified branch during the early migration;
- treat `ARCHIVE_CLOSED/` as mixed material that needs per-directory or per-file classification, not wholesale relocation;
- move `A_ARCHITECTURE`, explicit long-horizon design docs, and stable target-state papers toward `docs/architecture` once their scope is confirmed.

#### `root-plans`

- assume heavy mixing by default;
- preserve strong indexing because many documents point into this tree indirectly;
- avoid bulk moves until a reference audit is complete.

#### `backend-core`

- use `docs/implementation/backend-core` as the primary landing zone;
- route architecture notes to `docs/architecture/backend-core`;
- route governance-like operational baselines to `docs/governance/backend-core`.

#### `backend-docs`

- treat `main/`, most `B_API`, most `C_INGEST`, and most accepted test/ops material as implementation-leaning;
- keep stage-bound planning or review notes outside the implementation branch.

#### `ops-frontend`

- assume `main/` is mixed and needs file-level triage;
- move plan/review artifacts later than architecture and stable implementation docs, because this tree tends to blend multiple lifecycles.

#### `frontend-modern`

- keep it in a development-oriented bucket first;
- promote only the subset that becomes stable reference material.

## 8. Proposed Migration Phases

### Phase 0: Decision Freeze

Objective:

- confirm that the migration is a semantic reclassification project, not a simple rename;
- confirm the target root family and the compatibility requirement.

Outputs:

- one frozen destination taxonomy;
- one no-surprises rule for `development/latest-dev-docs` compatibility;
- one reviewed list of high-coupling references.

Exit criteria:

- the team agrees that `development/latest-dev-docs` remains readable during transition;
- the destination family is documented before any path move starts.

### Phase 1: Low-Ambiguity Inventory and Target Prep

Objective:

- identify which directories or files can move with minimal semantic debate;
- prepare missing destination roots under `docs/`.

Recommended first-pass candidates:

1. `development-plans/CURRENT_DEV/`
2. explicit `A_ARCHITECTURE/` trees
3. explicit `F_PLAN/` trees
4. obviously stable runbook-style `E_OPS/` documents

Serial vs parallel:

- serial: create destination taxonomy and naming rules;
- parallel: inventory low-ambiguity source files by subtree.

### Phase 2: First Migration Batch

Objective:

- move only low-ambiguity material to the approved destinations;
- leave mixed `main/` and mixed archive trees in place.

Expected result:

- the new root starts carrying real material;
- the old root still works as the entrypoint;
- broken-link risk is bounded to a smaller file set.

### Phase 3: Compatibility and Reference Repair

Objective:

- update high-value navigation and automation surfaces after the first batch is in place.

Minimum repair surface:

- root `README.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
- relevant `INDEX.md` files
- `codex_settings/AGENTS.md`
- `scripts/docs_only_workflow.sh`

### Phase 4: Mixed Trees and Archive Split

Objective:

- classify `main/` directories and mixed archive content at file level;
- avoid carrying semantic ambiguity into the new root.

Rule:

- when a directory contains both planning history and accepted implementation evidence, split the files instead of copying the whole directory unchanged.

### Phase 5: Closure and Legacy De-emphasis

Objective:

- make the new root the normal reading path;
- reduce `development/latest-dev-docs` to compatibility or archival status only after repeated validation.

Closure condition:

- core repo indexes, scripts, and current reading flows no longer rely on the old root as the sole canonical path.

## 9. Minimum Validation

This plan should only be considered execution-ready if all of the following minimum checks are attached to the migration batch:

### 9.1 Structural Validation

- verify target directories exist before moving content;
- verify moved files still have one clear authoritative location;
- verify no required source directory becomes orphaned without a replacement entrypoint.

### 9.2 Reference Validation

Run at least one repo-wide path scan covering the old and new roots, for example:

```bash
rg -n "development/latest-dev-docs|docs/development|docs/implementation|docs/architecture|docs/governance" \
  README.md codex_settings scripts docs development/latest-dev-docs
```

### 9.3 Navigation Validation

At minimum, manually verify that the following entrypoints still guide a reader to the correct content after each migration batch:

1. `development/latest-dev-docs/README.md`
2. `development/latest-dev-docs/MERGED_OVERVIEW.md`
3. `development/latest-dev-docs/development-plans/INDEX.md`
4. `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

### 9.4 Process Validation

- sample-check relative links from at least one moved directory;
- confirm scripts that reference the old root either still work or are explicitly updated in the same batch;
- confirm the migration notes explain which paths are authoritative and which are compatibility paths.

## 10. Risks and Rollback

### 10.1 Main Risks

- broken links in repo indexes and shell scripts;
- accidental duplication where both old and new paths look canonical;
- over-broad directory moves that hide semantic differences inside `main/` or archives;
- early removal of the old entrypoint while team habits and tooling still depend on it.

### 10.2 Rollback Policy

If a migration batch fails navigation or reference validation:

1. stop after the current batch and do not continue to mixed directories;
2. restore the previous authoritative path for the affected batch;
3. keep any new destination directories only if they are empty or clearly marked as not yet active;
4. record which references failed so the next attempt starts with link repair, not another move.

### 10.3 Safe Rollback Boundary

The safest rollback unit is one migration batch, not the entire docs tree. Each batch should be reversible without rewriting unrelated documentation.

## 11. Current Decision

The recommended direction is:

- do not treat this work as a simple `development/` to `docs/` rename;
- treat it as semantic reclassification plus staged path migration;
- keep `development/latest-dev-docs` as a compatibility entry until the new root proves stable;
- move low-ambiguity material first, then handle mixed `main/` and archive trees with file-level review.
