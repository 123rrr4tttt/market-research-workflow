# Atomic Tasklist: Search Brief / Critic / Retry Implementation

Date: 2026-03-25 (PST)
Owner: backend agent runtime + search + source-library
Parent: `12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md`
Reference Library: `13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md`

Parallel Wave Order: `15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md`

## 1. Scope and Deliverable

Goal:

- evolve the current agent runtime from one-shot search planning into a controlled iterative search policy.

Deliverable:

- one implementation track that adds `search brief`, then `critic`, then bounded retry, with tests and observability at each step.

## 2. Task Index

| AT ID | Topic | Phase | Depends On |
|---|---|---|---|
| AT-SB-00 | Freeze brief/critic/retry contracts | P0 | none |
| AT-SB-01 | Implement `search_brief` artifact generation | P0 | AT-SB-00 |
| AT-SB-02 | Persist brief into stage events and job metadata | P0 | AT-SB-01 |
| AT-SB-03 | Add observe-only `search_critic` stage | P1 | AT-SB-00, AT-SB-02 |
| AT-SB-04 | Define typed retry actions and field mutation rules | P1 | AT-SB-00 |
| AT-SB-05 | Add bounded single-round retry scheduler | P2 | AT-SB-03, AT-SB-04 |
| AT-SB-06 | Protect `source_library` rewritten params through runtime | P2 | AT-SB-04, AT-SB-05 |
| AT-SB-07 | Add observability events and metrics | P2 | AT-SB-02, AT-SB-03, AT-SB-05 |
| AT-SB-08 | Build benchmark and go/no-go rubric | P3 | AT-SB-03, AT-SB-05, AT-SB-07 |
| AT-SB-09 | Add limited branching mode for complex tasks only | P3 | AT-SB-05, AT-SB-08 |

## 2.1 Mandatory Reference Discipline

Every `AT-SB-*` implementation task must simultaneously reference all of the following before coding starts:

1. overall policy and architecture document: `12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md`
2. detailed reference library: `13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md`
3. current atomic task definition: this file
4. multi-agent wave order and gate constraints: `15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md`

Execution rule:

- no worker may implement an `AT-SB-*` item by reading only the atomic task text; the worker must also cite the relevant `12` sections and `13` reference IDs.
- each worker handoff must explicitly report:
  - which `12` sections were used,
  - which `13` reference IDs were used (`RL-*`, `LC-*`, `TC-*`),
  - which `15` wave/gate constraints were respected,
  - which recommendations were intentionally not adopted and why.

## 2.2 Indexed Required Reference Matrix

| AT ID | Overall Plan (`12`) | Reference Library (`13`) | Wave Order (`15`) | Validation |
|---|---|---|---|---|
| AT-SB-00 | `§4`, `§6.2`, `§10` | `LC-02`, `LC-04`, `TC-03` | `Wave-1`, contract freeze | `V-SB-01` |
| AT-SB-01 | `§4`, `§5.1`, `§6.1`, `§10` | `RL-01`, `RL-02`, `LC-01`, `TC-01` | `Wave-2` | `V-SB-02` |
| AT-SB-02 | `§5.1`, `§6.1`, `§6.3`, `§6.4` | `LC-01`, `LC-03`, `TC-01`, `TC-02` | `Wave-3` | `V-SB-02`, `V-SB-03` |
| AT-SB-03 | `§3.4`, `§5.2`, `§6.1`, `§10` | `RL-04`, `LC-01`, `TC-01` | `Wave-4` | `V-SB-01`, `V-SB-02` |
| AT-SB-04 | `§5.3`, `§6.2`, `§10` | `RL-04`, `LC-02`, `TC-03` | `Wave-2` | `V-SB-01`, `V-SB-03` |
| AT-SB-05 | `§3.2`, `§5.3`, `§6.1`, `§6.3`, `§10` | `RL-02`, `RL-04`, `LC-01`, `LC-03`, `TC-01`, `TC-02` | `Wave-5` | `V-SB-02`, `V-SB-03` |
| AT-SB-06 | `§5.3`, `§6.2`, `§6.4`, `§10` | `LC-02`, `LC-05`, `TC-04` | `Wave-6` | `V-SB-04`, `V-SB-05` |
| AT-SB-07 | `§6.4`, `§7.2`, `§10` | `RL-05`, `RL-06`, `LC-01`, `LC-03`, `TC-02` | `Wave-6` | `V-SB-02`, `V-SB-03`, `V-SB-06` |
| AT-SB-08 | `§7.1`, `§7.2`, `§7.3`, `§8`, `§10` | `RL-05`, `LC-10`, `TC-01`, `TC-02`, `TC-04` | `Wave-7` | benchmark gate |
| AT-SB-09 | `§3.3`, `§8`, `§10` | `RL-03`, `LC-01`, `TC-01` | `Wave-8` | benchmark validation sample |

## 3. Atomic Tasks

### P0 Foundation

### AT-SB-00 Freeze brief/critic/retry contracts
- Required References:
  - `12`: `§4`, `§6.2`, `§10`
  - `13`: `LC-02`, `LC-04`, `TC-03`
  - `15`: `Wave-1`, contract freeze rules
- Target:
  - define canonical schemas for `search_brief`, `search_critic`, and `retry_action`.
- Input:
  - `12_*` policy doc,
  - `task_contract.py`,
  - current `search.market` and `source_library` task contracts.
- Output:
  - shared contract helpers and schema snapshots.
- Acceptance:
  - all new runtime artifacts have explicit required/optional fields,
  - retry-eligible fields are explicitly enumerated by channel,
  - no new free-form mutable blobs.
- Minimal gate:
  - planner/contract unit tests.

### AT-SB-01 Implement `search_brief` artifact generation
- Required References:
  - `12`: `§4`, `§5.1`, `§6.1`, `§10`
  - `13`: `RL-01`, `RL-02`, `LC-01`, `TC-01`
  - `15`: `Wave-2`, Worker-Loop ownership
- Target:
  - generate one structured `search_brief` before final task execution.
- Input:
  - raw NL request,
  - planner draft tasks,
  - current autonomous source-library mounting hints.
- Output:
  - `search_brief` artifact with `coverage_axes`, `time_strategy`, `search_strategies`, `source_preferences`, and `stop_conditions`.
- Acceptance:
  - brief exists for eligible research-style requests,
  - brief remains deterministic enough for tests,
  - brief does not change executable task contract silently.
- Minimal gate:
  - loop unit tests.

### AT-SB-02 Persist brief into stage events and job metadata
- Required References:
  - `12`: `§5.1`, `§6.1`, `§6.3`, `§6.4`
  - `13`: `LC-01`, `LC-03`, `TC-01`, `TC-02`
  - `15`: `Wave-3`, persistence gate ordering
- Target:
  - make `search_brief` observable and replay-friendly.
- Input:
  - brief artifact from AT-SB-01.
- Output:
  - stage event and metadata persistence path.
- Acceptance:
  - brief can be retrieved through job state or events,
  - trace continuity remains intact,
  - no contract regression on existing APIs.
- Minimal gate:
  - API + loop tests.

### P1 Critic Introduction

### AT-SB-03 Add observe-only `search_critic` stage
- Required References:
  - `12`: `§3.4`, `§5.2`, `§6.1`, `§10`
  - `13`: `RL-04`, `LC-01`, `TC-01`
  - `15`: `Wave-4`, observe-only constraint
- Target:
  - score search quality without yet changing runtime behavior.
- Input:
  - first-round search results,
  - brief artifact,
  - user goal.
- Output:
  - `search_critic` result with score, diagnosis, and proposed next action.
- Acceptance:
  - critic runs after eligible first-round searches,
  - critic can output `stop` or `retry` proposal,
  - observe-only mode never mutates tasks.
- Minimal gate:
  - loop unit tests and contract assertions.

### AT-SB-04 Define typed retry actions and field mutation rules
- Required References:
  - `12`: `§5.3`, `§6.2`, `§10`
  - `13`: `RL-04`, `LC-02`, `TC-03`
  - `15`: `Wave-2`, Worker-Contract ownership
- Target:
  - prevent uncontrolled query rewriting.
- Input:
  - current task contract helpers,
  - critic output design.
- Output:
  - finite retry action set and per-channel rewrite rules.
- Acceptance:
  - allowed actions are explicit,
  - disallowed field mutation fails closed,
  - `source_library` and `search.market` use the same governance model.
- Minimal gate:
  - planner/API contract tests.

### P2 Controlled Retry

### AT-SB-05 Add bounded single-round retry scheduler
- Required References:
  - `12`: `§3.2`, `§5.3`, `§6.1`, `§6.3`, `§10`
  - `13`: `RL-02`, `RL-04`, `LC-01`, `LC-03`, `TC-01`, `TC-02`
  - `15`: `Wave-5`, retry scheduler serial gate
- Target:
  - allow one automatic corrective search round.
- Input:
  - critic output,
  - retry action rules,
  - retry budget policy.
- Output:
  - runtime retry scheduling path.
- Acceptance:
  - retry only happens when critic score is below threshold,
  - one extra round is the default cap,
  - retry reason is persisted and auditable.
- Minimal gate:
  - loop tests with retry/no-retry matrix.

### AT-SB-06 Protect `source_library` rewritten params through runtime
- Required References:
  - `12`: `§5.3`, `§6.2`, `§6.4`, `§10`
  - `13`: `LC-02`, `LC-05`, `TC-04`
  - `15`: `Wave-6`, Worker-SourceLib ownership
- Target:
  - ensure retried source-library tasks remain contract-valid and behaviorally effective.
- Input:
  - rewritten top-level fields,
  - collect runtime parser,
  - ingest/source-library contract tests.
- Output:
  - stable rewrite path for `query_terms`, `provider`, `language`, `source_mode`, `urls`, `max_items`.
- Acceptance:
  - runtime consumes rewritten values correctly,
  - no drift between retry payload and runtime parser,
  - ingest/source-library tests stay green.
- Minimal gate:
  - runtime + core-business tests.

### AT-SB-07 Add observability events and metrics
- Required References:
  - `12`: `§6.4`, `§7.2`, `§10`
  - `13`: `RL-05`, `RL-06`, `LC-01`, `LC-03`, `TC-02`
  - `15`: `Wave-6`, event wiring without retry-control drift
- Target:
  - expose enough state for evaluation and later policy learning.
- Input:
  - brief, critic, retry lifecycle.
- Output:
  - event taxonomy and metrics counters.
- Acceptance:
  - event names are stable,
  - retry outcome and critic score are queryable,
  - no missing trace linkage.
- Minimal gate:
  - metrics schema tests.

### P3 Rollout and Evaluation

### AT-SB-08 Build benchmark and go/no-go rubric
- Required References:
  - `12`: `§7.1`, `§7.2`, `§7.3`, `§8`, `§10`
  - `13`: `RL-05`, `LC-10`, `TC-01`, `TC-02`, `TC-04`
  - `15`: `Wave-7`, benchmark gate
- Target:
  - evaluate whether critic and retry actually improve outcome quality.
- Input:
  - prompt set across market research categories,
  - event logs and final outputs.
- Output:
  - benchmark pack and scoring rubric.
- Acceptance:
  - positive or neutral retry uplift is measurable,
  - false-positive retry rate is visible,
  - latency/cost tradeoff is explicit.
- Minimal gate:
  - benchmark script or documented rubric run.

### AT-SB-09 Add limited branching mode for complex tasks only
- Required References:
  - `12`: `§3.3`, `§8`, `§10`
  - `13`: `RL-03`, `LC-01`, `TC-01`
  - `15`: `Wave-8`, branching stays default-off
- Target:
  - allow 2-3 strategy variants for selected high-ambiguity prompts.
- Input:
  - brief artifact,
  - retry/critic framework,
  - benchmark evidence.
- Output:
  - optional reduced branching path.
- Acceptance:
  - not enabled by default,
  - branch fan-out remains capped,
  - branch outcome comparison is observable.
- Minimal gate:
  - loop tests + benchmark sample validation.

## 4. Execution Sequence

1. AT-SB-00
2. AT-SB-01 AT-SB-02
3. AT-SB-03 AT-SB-04
4. AT-SB-05 AT-SB-06 AT-SB-07
5. AT-SB-08
6. AT-SB-09

## 5. Indexed Validation Map

| Validation ID | Scope | Command family |
|---|---|---|
| V-SB-01 | planner / contract | `pytest tests/unit/test_agent_batch_planner_unittest.py` |
| V-SB-02 | loop behavior | `pytest tests/unit/test_agent_batch_loop_unittest.py` |
| V-SB-03 | API metadata / submission | `pytest tests/unit/test_agent_batch_api_unittest.py` |
| V-SB-04 | source-library runtime rewrite | `pytest tests/unit/test_collect_runtime_source_library_adapter_unittest.py` |
| V-SB-05 | ingest/source-library contract protection | `pytest tests/core_business/test_ingest_core_contract.py` |
| V-SB-06 | skill/runtime manifest alignment | `pytest tests/unit/test_skill_runtime_unittest.py` |

## 6. Done Criteria

- `search_brief` is observable and stable.
- `search_critic` exists and can score without mutating runtime in observe-only mode.
- bounded retry is auditable and fail-closed.
- rewritten search parameters remain inside shared task contract governance.
- source-library path does not regress.
- benchmark and rollout gate exist before broader enablement.

## 7. Rollout Constraints

Must do:

- keep current task contract discipline,
- keep retry budget explicit,
- keep branch fan-out disabled by default,
- keep all new fields replay-friendly and observable.

Must not do:

- unbounded search loops,
- free-form retry mutations,
- silently enable branching for all tasks,
- mix RL/policy-learning scope into first implementation wave.
