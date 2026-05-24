# Multi-Agent Wave Execution Order: Search Brief / Critic / Retry (2026-03-25)

Date: 2026-03-25 (PST)
Scope: multi-round subagent parallel development plan for `AT-SB-00 ~ AT-SB-09`
Parent: `14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md`
Reference Library: `13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md`

## 1. Purpose

This note converts the atomic task list into a wave-based execution order suitable for multi-round subagent parallel development.

Goals:

1. maximize safe parallelism,
2. minimize file conflicts,
3. keep contract-governed behavior stable,
4. ensure each wave has a clear gate before the next wave starts.

## 2. Parallelism Summary

Only two groups are good candidates for true same-wave parallel development:

1. `AT-SB-01` with `AT-SB-04`
2. `AT-SB-06` with `AT-SB-07`

Everything else is on the critical path and should stay serial or serial-with-review.

Reason:

- `task_contract.py` and `agent_loop.py` are shared hotspots,
- `search_brief`, `search_critic`, and `retry_action` must be frozen before downstream workers implement against them,
- runtime rewrite and event instrumentation should not be racing the main retry scheduler changes.

## 2.1 Wave Kickoff Reference Rule

Every wave kickoff package must include references from all four layers:

1. overall plan: `12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md`
2. reference library: `13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md`
3. atomic task definition: `14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md`
4. current wave constraints: this file

No worker may be assigned only an `AT-SB-*` label without the corresponding `12/13/14/15` reference packet.

Required worker kickoff template:

- `Task`: exact `AT-SB-*` item(s)
- `Plan Sections`: exact `12` sections
- `Reference IDs`: exact `13` IDs (`RL-*`, `LC-*`, `TC-*`)
- `Wave Constraints`: exact `15` wave, ownership, and gate rules
- `Output Contract`: changed files + validation gate + unresolved risks

## 2.2 Wave-to-Reference Map

| Wave | Required Overall Plan (`12`) | Required Reference Library (`13`) | Required Atomic Task (`14`) |
|---|---|---|---|
| Wave-1 | `§4`, `§6.2`, `§10` | `LC-02`, `LC-04`, `TC-03` | `AT-SB-00` |
| Wave-2 | `§4`, `§5.1`, `§5.3`, `§6.1`, `§6.2`, `§10` | `RL-01`, `RL-02`, `RL-04`, `LC-01`, `LC-02`, `TC-01`, `TC-03` | `AT-SB-01`, `AT-SB-04` |
| Wave-3 | `§5.1`, `§6.1`, `§6.3`, `§6.4` | `LC-01`, `LC-03`, `TC-01`, `TC-02` | `AT-SB-02` |
| Wave-4 | `§3.4`, `§5.2`, `§6.1`, `§10` | `RL-04`, `LC-01`, `TC-01` | `AT-SB-03` |
| Wave-5 | `§3.2`, `§5.3`, `§6.1`, `§6.3`, `§10` | `RL-02`, `RL-04`, `LC-01`, `LC-03`, `TC-01`, `TC-02` | `AT-SB-05` |
| Wave-6 | `§5.3`, `§6.2`, `§6.4`, `§7.2`, `§10` | `LC-02`, `LC-05`, `RL-05`, `RL-06`, `TC-02`, `TC-04` | `AT-SB-06`, `AT-SB-07` |
| Wave-7 | `§7.1`, `§7.2`, `§7.3`, `§8`, `§10` | `RL-05`, `LC-10`, `TC-01`, `TC-02`, `TC-04` | `AT-SB-08` |
| Wave-8 | `§3.3`, `§8`, `§10` | `RL-03`, `LC-01`, `TC-01` | `AT-SB-09` |

## 3. Shared Hotspots

Highest-conflict files:

1. `main/backend/app/services/agent_batch/task_contract.py`
2. `main/backend/app/services/agent_batch/agent_loop.py`
3. `main/backend/app/api/agent_batch.py`
4. `main/backend/app/services/collect_runtime/runtime.py`
5. `main/backend/app/services/skill_runtime.py`

Highest-conflict tests:

1. `main/backend/tests/unit/test_agent_batch_loop_unittest.py`
2. `main/backend/tests/unit/test_agent_batch_api_unittest.py`
3. `main/backend/tests/unit/test_agent_batch_planner_unittest.py`
4. `main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`
5. `main/backend/tests/core_business/test_ingest_core_contract.py`

Rule:

- do not assign the same hotspot file to more than one worker in the same wave.

## 4. Contract Freeze Before Parallelism

The following must be frozen in `Wave-1` before downstream workers start:

1. `search_brief` schema
2. `search_critic` schema
3. `retry_action` enum and payload shape
4. rewrite-eligible field allowlist for `search.market`
5. rewrite-eligible field allowlist for `source_library`
6. retry policy defaults:
   - `budget = 1`
   - bounded single-round retry
   - branching disabled by default
7. event and metadata names for `brief/critic/retry`

Without this freeze, parallel implementation will drift.

## 5. Worker Ownership Model

### Worker-Contract

Primary ownership:

- `main/backend/app/services/agent_batch/task_contract.py`
- `main/backend/tests/unit/test_agent_batch_planner_unittest.py`

Best for:

- `AT-SB-00`
- `AT-SB-04`

### Worker-Loop

Primary ownership:

- `main/backend/app/services/agent_batch/agent_loop.py`
- `main/backend/tests/unit/test_agent_batch_loop_unittest.py`

Best for:

- `AT-SB-01`
- `AT-SB-03`
- `AT-SB-05`
- `AT-SB-09`

### Worker-API

Primary ownership:

- `main/backend/app/api/agent_batch.py`
- `main/backend/app/services/skill_runtime.py`
- `main/backend/tests/unit/test_agent_batch_api_unittest.py`

Best for:

- `AT-SB-02`
- selected metadata parts of `AT-SB-07`

### Worker-SourceLib

Primary ownership:

- `main/backend/app/services/collect_runtime/runtime.py`
- `main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`
- `main/backend/tests/core_business/test_ingest_core_contract.py`

Best for:

- `AT-SB-06`

### Worker-Bench

Primary ownership:

- benchmark script/config path
- rollout docs / evaluation pack

Best for:

- `AT-SB-08`

## 6. Wave Order

### Wave-1 Contract Freeze

Worker count:

- `1`

Tasks:

- `AT-SB-00`

Output:

- frozen `search_brief/search_critic/retry_action` contracts,
- frozen rewrite allowlist and retry defaults.

Gate:

- `V-SB-01`

Why serial:

- every later worker depends on this definition.

### Wave-2 First Safe Parallel Split

Worker count:

- `2`

Tasks:

- Worker-Loop: `AT-SB-01`
- Worker-Contract: `AT-SB-04`

Output:

- `search_brief` artifact generation,
- typed retry actions and field mutation rules.

Gate:

- `V-SB-02`
- `V-SB-01`

Why parallel is safe:

- one worker focuses on brief generation in `agent_loop.py`,
- the other freezes mutation governance in `task_contract.py`,
- write domains are separable enough if test-file ownership is also split.

### Wave-3 Brief Persistence

Worker count:

- `1`

Tasks:

- `AT-SB-02`

Output:

- `search_brief` in stage events / metadata / API-visible state.

Gate:

- `V-SB-02`
- `V-SB-03`

Why serial:

- persistence depends on the actual brief artifact shape from Wave-2.

### Wave-4 Observe-Only Critic

Worker count:

- `1`

Tasks:

- `AT-SB-03`

Output:

- observe-only `search_critic`
- `stop/retry` proposal without mutation.

Gate:

- `V-SB-01`
- `V-SB-02`

Why serial:

- critic depends on both contract freeze and brief persistence.

### Wave-5 Retry Scheduler

Worker count:

- `1`

Tasks:

- `AT-SB-05`

Output:

- bounded single-round retry scheduler,
- persisted retry reason and budget handling.

Gate:

- `V-SB-02`
- `V-SB-03`

Why serial:

- scheduler must be built after both critic and retry action rules are stable.

### Wave-6 Second Safe Parallel Split

Worker count:

- `2`

Tasks:

- Worker-SourceLib: `AT-SB-06`
- Worker-API or Worker-Loop: `AT-SB-07`

Output:

- source-library rewritten params consumed safely,
- event taxonomy and metrics counters added.

Gate:

- `V-SB-04`
- `V-SB-05`
- `V-SB-06`
- loop/event assertions as needed

Why parallel is only conditionally safe:

- `AT-SB-06` should stay off `agent_loop.py`,
- `AT-SB-07` should avoid changing retry control flow and focus on event wiring / metric emission,
- if `AT-SB-07` needs heavy `agent_loop.py` changes, collapse this wave back to serial.

### Wave-7 Benchmark and Go/No-Go

Worker count:

- `1`

Tasks:

- `AT-SB-08`

Output:

- benchmark pack,
- scoring rubric,
- rollout gate.

Gate:

- benchmark sample run or documented rubric execution.

Why serial:

- it depends on the final observable retry behavior.

### Wave-8 Optional Branching

Worker count:

- `1`

Tasks:

- `AT-SB-09`

Output:

- reduced branching mode for selected complex tasks,
- default remains off.

Gate:

- `V-SB-02`
- benchmark validation sample

Why serial:

- branching should not be introduced before the single-retry path is stable and measured.

## 7. Combinations That Must Not Run In The Same Wave

1. `AT-SB-00` with any implementation task
2. `AT-SB-03` before `AT-SB-02`
3. `AT-SB-05` before `AT-SB-04`
4. `AT-SB-06` before `AT-SB-05`
5. `AT-SB-05` and `AT-SB-07` if both need heavy `agent_loop.py` edits
6. `AT-SB-06` and any concurrent `task_contract.py` semantic change
7. `AT-SB-09` before `AT-SB-08`

## 8. Failure Isolation Rules

1. if a wave has two workers, each worker owns a disjoint write set
2. each worker runs only its minimum gate before merge
3. if one worker fails, do not block the other from finishing its own gate
4. merge conflicts in hotspot tests are resolved immediately before the next wave starts
5. do not carry unresolved contract changes into the next wave

## 9. Recommended Practical Rollout

If the team wants the safest path:

1. Wave-1
2. Wave-2
3. Wave-3
4. Wave-4
5. Wave-5
6. Wave-6 only if write domains stay separate
7. Wave-7
8. Wave-8 optional

If the team wants the shortest path with moderate risk:

1. Wave-1
2. Wave-2
3. Wave-3
4. Wave-4
5. Wave-5
6. Wave-6 parallel
7. Wave-7
8. Wave-8 only after benchmark pass

## 10. Final Recommendation

Recommended default execution order:

1. `Wave-1: AT-SB-00`
2. `Wave-2: AT-SB-01 || AT-SB-04`
3. `Wave-3: AT-SB-02`
4. `Wave-4: AT-SB-03`
5. `Wave-5: AT-SB-05`
6. `Wave-6: AT-SB-06 || AT-SB-07`
7. `Wave-7: AT-SB-08`
8. `Wave-8: AT-SB-09`

In practice, this is an `8-wave` plan with only `2` genuinely parallel waves.

That is the right trade-off for this topic because the contract and runtime-control surfaces are still concentrated in a small number of shared files.
