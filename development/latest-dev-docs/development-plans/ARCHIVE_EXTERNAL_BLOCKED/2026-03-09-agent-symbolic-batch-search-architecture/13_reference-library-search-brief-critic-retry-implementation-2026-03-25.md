# Reference Library: Search Brief / Critic / Retry Implementation (2026-03-25)

Date: 2026-03-25 (PST)
Scope: `search brief -> search critic -> bounded retry` for `search.market` and `source_library`
Parent: `12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md`

## 1. Purpose

This reference library is the implementation companion for the selected architecture.

It is designed to answer four questions quickly:

1. which external research ideas are actually relevant,
2. which local modules are the primary change anchors,
3. which existing tests should be extended first,
4. which pieces are implementation-ready now versus later-stage.

## 2. Reference Index

### 2.1 External strategy references

| ID | Topic | Why it matters | Primary source |
|---|---|---|---|
| RL-01 | decomposition-first planning | shapes first-pass query and source strategy | `Self-Ask` / `Plan-and-Solve` |
| RL-02 | reasoning-action loop | supports observation-driven search rewrite | `ReAct` |
| RL-03 | bounded branching | supports 2-3 search strategy variants for hard tasks | `Tree of Thoughts` |
| RL-04 | retrieval-quality critique | supports retry gating and correction | `Reflexion`, `Self-RAG`, `CRAG`, `Probing-RAG` |
| RL-05 | learned search policy | later-stage search optimization | `Search-R1` |
| RL-06 | long-horizon research agent | end-state reference only | `WebThinker`, `OpenAI Deep Research` |

### 2.2 Local implementation anchors

| ID | Path | Role in next implementation |
|---|---|---|
| LC-01 | `main/backend/app/services/agent_batch/agent_loop.py` | add `search_brief`, critic step, and bounded retry loop |
| LC-02 | `main/backend/app/services/agent_batch/task_contract.py` | define brief/critic/retry schemas and rewrite-eligible fields |
| LC-03 | `main/backend/app/api/agent_batch.py` | store retry metadata and surface iterative-mode control |
| LC-04 | `main/backend/app/services/skill_runtime.py` | keep planner-visible manifest and dispatch metadata aligned |
| LC-05 | `main/backend/app/services/collect_runtime/runtime.py` | consume rewritten `source_library` parameters cleanly |
| LC-06 | `main/backend/tests/unit/test_agent_batch_loop_unittest.py` | primary unit-test anchor for loop behavior |
| LC-07 | `main/backend/tests/unit/test_agent_batch_api_unittest.py` | API-side retry metadata and submission contract tests |
| LC-08 | `main/backend/tests/unit/test_agent_batch_planner_unittest.py` | planner and schema alignment tests |
| LC-09 | `main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py` | source-library parameter rewrite consumption tests |
| LC-10 | `main/backend/tests/core_business/test_ingest_core_contract.py` | source-library ingest-path contract protection |

## 3. External Reference Notes

### RL-01 Decomposition-first planning

Primary sources:

- `Self-Ask`: [https://arxiv.org/abs/2210.03350](https://arxiv.org/abs/2210.03350)
- `Plan-and-Solve Prompting`: [https://arxiv.org/abs/2305.04091](https://arxiv.org/abs/2305.04091)

Implementation value:

- derive `coverage_axes`, `time_strategy`, `source_preferences`, and `search_strategies` before execution,
- reduce low-quality first-pass search by making query intent explicit,
- cleanly maps to the current task contract surface.

What to borrow now:

- structured `search brief`
- subtopic decomposition
- explicit stop conditions

What not to over-copy:

- free-form multi-hop decomposition with no task-budget limit

### RL-02 ReAct

Primary source:

- `ReAct`: [https://arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)

Implementation value:

- provides the loop shape for `observe -> diagnose -> rewrite -> act`,
- naturally fits the existing `search.market` plus `source_library` dual-channel runtime.

What to borrow now:

- explicit observation-aware second pass
- bounded step loop
- stage-level traceability

What not to over-copy:

- unconstrained chain-of-thought-style looping without typed retry actions

### RL-03 Tree of Thoughts

Primary source:

- `Tree of Thoughts`: [https://arxiv.org/abs/2305.10601](https://arxiv.org/abs/2305.10601)

Implementation value:

- useful only when one query strategy is likely insufficient,
- relevant for high-ambiguity research prompts.

What to borrow now:

- limited branching categories:
  - broad recall
  - precision entity scan
  - source-library-first

What not to over-copy:

- deep search trees or large branch fans in default runtime

### RL-04 Retrieval-quality critic

Primary sources:

- `Reflexion`: [https://arxiv.org/abs/2303.11366](https://arxiv.org/abs/2303.11366)
- `Self-RAG`: [https://arxiv.org/abs/2310.11511](https://arxiv.org/abs/2310.11511)
- `CRAG`: [https://arxiv.org/abs/2401.15884](https://arxiv.org/abs/2401.15884)
- `Probing-RAG`: [https://arxiv.org/abs/2410.13339](https://arxiv.org/abs/2410.13339)

Implementation value:

- gives the rationale for deciding whether current search quality is enough,
- provides the conceptual basis for `critic score`, `diagnosis`, and `next_action`.

What to borrow now:

- critique before retry
- explicit correction actions
- retrieval-quality features:
  - entity coverage
  - source diversity
  - freshness fit
  - novelty gain
  - goal alignment

What not to over-copy:

- large learned gating stack before baseline metrics exist

### RL-05 Learned search policy

Primary source:

- `Search-R1`: [https://arxiv.org/abs/2503.09516](https://arxiv.org/abs/2503.09516)

Implementation value:

- informs future trajectory logging and policy-learning design.

What to borrow now:

- log actions, observations, and outcomes in a replay-friendly structure

What to defer:

- RL training itself
- reward-model investment
- offline policy optimization pipeline

### RL-06 Long-horizon research systems

Primary sources:

- `WebThinker`: [https://arxiv.org/abs/2504.21776](https://arxiv.org/abs/2504.21776)
- `OpenAI Deep Research System Card`: [https://openai.com/index/deep-research-system-card/](https://openai.com/index/deep-research-system-card/)

Implementation value:

- sets the north-star direction for eventual deep-research runtime.

What to borrow now:

- stage visibility
- pivot logging
- browse/search/report separation

What to defer:

- generalized autonomous browsing loop
- fully long-horizon report synthesis coupling in the same rollout

## 4. Local Code Reference Map

### LC-01 `agent_loop.py`

Current relevance:

- already owns NL task normalization and autonomous source-library mounting.

Expected next responsibilities:

1. build `search_brief`
2. persist `search_brief` into stage state/events
3. schedule first execution round
4. evaluate `search_critic`
5. if needed, trigger bounded retry rewrite

Primary risks:

- introducing loops that bypass current fail-closed contract handling
- retry actions mutating fields outside task contract allowlist

### LC-02 `task_contract.py`

Current relevance:

- centralizes planner/task/dispatch/execution contract ownership.

Expected next responsibilities:

1. define brief schema
2. define critic schema
3. define retry action schema
4. define rewrite-eligible fields per channel
5. define retry-budget defaults and branch limits

Primary risks:

- adding new runtime semantics without consolidating them into contract helpers

### LC-03 `agent_batch.py`

Current relevance:

- controls submit-time channel handling, execution registry, approval binding, and metadata shaping.

Expected next responsibilities:

1. accept iterative-mode flag or policy control
2. persist retry diagnostics in job/item metadata
3. expose stage events and retry counts through API surfaces

Primary risks:

- metadata growth without schema discipline
- state becoming API-visible before stable contract is frozen

### LC-04 `skill_runtime.py`

Current relevance:

- bootstraps manifest-facing skill registration.

Expected next responsibilities:

- keep planner-visible behavior aligned with brief/critic-enabled runtime evolution.

Primary risks:

- planner-visible capabilities drifting from actual loop behavior

### LC-05 `collect_runtime/runtime.py`

Current relevance:

- consumes `source_library` search controls.

Expected next responsibilities:

- accept rewritten `query_terms`, `source_mode`, `provider`, `language`, `urls`, and related fields without ambiguity.

Primary risks:

- retry rewrites generating values that runtime accepts inconsistently

## 5. Test Reference Map

### TC-01 Loop behavior

Primary path:

- `main/backend/tests/unit/test_agent_batch_loop_unittest.py`

Add coverage for:

- `search_brief` creation
- observe-only critic mode
- retry trigger conditions
- retry budget exhaustion
- no-retry when critic score is sufficient

### TC-02 API and metadata

Primary path:

- `main/backend/tests/unit/test_agent_batch_api_unittest.py`

Add coverage for:

- iterative-mode request flag
- retry metadata surfacing
- invalid retry action rejection
- fail-closed behavior for unsupported rewritten fields

### TC-03 Planner/contract alignment

Primary path:

- `main/backend/tests/unit/test_agent_batch_planner_unittest.py`

Add coverage for:

- brief schema generation from planner context
- retry action schema alignment with contract helper outputs

### TC-04 Source-library rewrite consumption

Primary path:

- `main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py`
- `main/backend/tests/core_business/test_ingest_core_contract.py`

Add coverage for:

- rewritten `source_library` params survive and remain contract-valid
- retry does not regress ingest/source-library contract expectations

## 6. Recommended Read Order

1. `12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md`
2. this reference library
3. follow-up atomic task list
4. local code anchors in `agent_loop.py`, `task_contract.py`, `agent_batch.py`
5. loop/API/planner/runtime test anchors

## 7. Freeze Recommendations

Freeze now:

1. `search brief` as the first implementation phase
2. `critic` as observe-only before automatic retry
3. retry budget of `1` extra round by default
4. branch fan-out disabled by default

Do not freeze yet:

1. RL learning path
2. generalized deep-research browsing loop
3. branch search as default runtime mode
