# Parallel Wave Plan: Source-Library / Ingest Minimal Migration

Updated: 2026-03-26 PST

## Purpose

This file is the execution plan for running the current migration topic by
parallel waves while preserving the task-number-driven workflow.

Subagents must execute by `AT-SLIM-*` task number and repository rules.
They should derive details from the plan, atomic task list, and reference
pack instead of relying on a custom decomposition from the main agent.

## Source Of Truth

Execution order and acceptance are defined by:

- [01_source-library-ingest-minimal-migration-plan-2026-03-25.md](./01_source-library-ingest-minimal-migration-plan-2026-03-25.md)
- [02_wave0-freeze-and-acceptance-contract-2026-03-26.md](./02_wave0-freeze-and-acceptance-contract-2026-03-26.md)
- [03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md](./03_atomic-tasklist-source-library-ingest-minimal-migration-2026-03-26.md)
- [references/INDEX.md](./references/INDEX.md)

## Global Execution Rule

For this topic:

1. every subagent executes against a task number
2. every subagent must read the task definition and required references
   itself
3. every subagent must follow repository development rules and atomic-task
   acceptance rules
4. every subagent returns:
   - result
   - changed files
   - validation status
   - risk
5. if a subagent is blocked by missing context, contract conflict, or
   overlapping ownership, it stops and reports the blocker instead of
   inventing extra structure

## Ownership Rule For Parallel Waves

Parallel work is allowed only when write scopes are low-coupling.

Wave 1 ownership is frozen as:

- `AT-SLIM-02`: regression baseline and tests
- `AT-SLIM-03`: node mapping and caller matrix docs
- `AT-SLIM-04`: compat and observability invariant docs

The main agent remains responsible for:

- shared status integration
- later serial waves
- merge decisions if outputs conflict

## Wave Layout

### Wave 0. Serial Freeze

- Tasks:
  - `AT-SLIM-01`
- Status:
  - complete when [02_wave0-freeze-and-acceptance-contract-2026-03-26.md](./02_wave0-freeze-and-acceptance-contract-2026-03-26.md) exists and the two newly frozen reference contracts are linked from the plan and task list
- Why serial:
  - all later tasks depend on the same frozen execution contract

### Wave 1. Parallel Freeze Pack

- Tasks:
  - `AT-SLIM-02`
  - `AT-SLIM-03`
  - `AT-SLIM-04`
- Parallelization rule:
  - run in parallel because acceptance surfaces are related but write
    scopes are still separable
- Expected outputs:
  - `AT-SLIM-02`: regression pack and missing-gap note if needed
  - `AT-SLIM-03`: touched-node execution sheet and caller matrix
  - `AT-SLIM-04`: compat / observability invariant list
- Exit gate:
  - all three tasks must finish before any structural code move begins

### Wave 2. Serial Shared-Helper Extraction

- Tasks:
  - `AT-SLIM-05`
  - `AT-SLIM-06`
- Serial reason:
  - both tasks touch the same core runtime path and helper boundary
  - `AT-SLIM-06` depends on the output of `AT-SLIM-05`

### Wave 3. Serial Call-Graph Switch

- Tasks:
  - `AT-SLIM-07`
  - `AT-SLIM-08`
- Serial reason:
  - both tasks reshape the same `collect_urls_from_list(...)` /
    frontdoor convergence corridor

### Wave 4. Rollout And Closure

- Tasks:
  - `AT-SLIM-09`
  - `AT-SLIM-10`
- Execution rule:
  - `AT-SLIM-09` is the critical path
  - `AT-SLIM-10` may prepare closure artifacts in parallel, but final
    closure waits for `AT-SLIM-09` completion

## Subagent Start Contract

Each Wave 1 subagent should receive only:

- the task number it owns
- the current topic root path
- the rule that it must follow the task definition and references itself

The main agent should not decompose the task into custom sub-steps unless
needed to resolve a blocker.

## Wave 1 Validation Floor

Before Wave 1 is considered complete, the combined evidence should cover:

- regression baseline visibility
- node mapping visibility
- compat / observability visibility

At minimum this should still be runnable:

- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_resolver_unittest.py main/backend/tests/unit/test_source_library_item_resolver_unittest.py`
- `python3.11 -m pytest -q main/backend/tests/unit/test_source_library_terminal_output_unittest.py main/backend/tests/unit/test_postprocess_frontdoor_unittest.py`
- `python3.11 -m pytest -q main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py main/backend/tests/unit/test_source_library_handler_cluster_frontdoor_unittest.py`

## Do-Not-Parallelize List

The following tasks should not be executed in parallel with each other:

- `AT-SLIM-05` and `AT-SLIM-06`
- `AT-SLIM-07` and `AT-SLIM-08`
- any two tasks that both need to rewrite
  `main/backend/app/services/ingest/url_pool.py`

## Recommended Next Commanding Pattern

1. start Wave 1 subagents for `AT-SLIM-02`, `AT-SLIM-03`, `AT-SLIM-04`
2. wait for all Wave 1 outputs
3. integrate statuses
4. start Wave 2 serial execution
