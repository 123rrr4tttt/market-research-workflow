# Search Brief / Critic / Retry Policy and Agent Strategy Selection (2026-03-25)

## 1. Summary

This note sets the next practical evolution step for the current `agent_batch` runtime.

Main line:

1. add a `search brief` stage before executable tasks,
2. add a post-search `critic` stage that scores search quality,
3. add a bounded `retry / pivot` policy that rewrites search parameters when quality is insufficient.

Supporting line:

- include a technical comparison of external agent strategies and explain which pieces should be borrowed now versus deferred.

Primary conclusion:

- the project should not jump directly to RL-trained search agents,
- the best near-term architecture is a hybrid of `Plan-and-Solve` + `ReAct` + `CRAG-lite`,
- `Tree-of-Thoughts` style branching should be reserved for high-value complex research tasks only,
- `Search-R1` / deep-research-style training should be treated as a later-stage optimization path after enough trajectories exist.

## 2. Why This Is the Right Next Step

The current runtime has already closed the highest-risk contract gaps for `search.market` and `source_library`:

- planner-visible task schema is materially closer to runtime-effective schema,
- `override_params` is allowlist-governed,
- `source_library` top-level execution parameters are promoted and preserved,
- channel dispatch / lane / approval / execution metadata is centralized in shared task contract helpers.

What is still missing is not another task type. What is missing is a stronger search policy between:

1. user intent,
2. first search parameter selection,
3. search result evaluation,
4. second-step query rewrite or source pivot.

That is exactly the problem solved by a `search brief -> act -> critic -> retry` loop.

## 3. Technical Strategy Survey

This section is intentionally selective. It focuses only on strategies that directly help search-parameter design and search-path control.

### 3.1 Decomposition-first strategies

Representative sources:

- `Self-Ask`: [https://arxiv.org/abs/2210.03350](https://arxiv.org/abs/2210.03350)
- `Plan-and-Solve Prompting`: [https://arxiv.org/abs/2305.04091](https://arxiv.org/abs/2305.04091)

Key idea:

- split the user goal into smaller subquestions or a short plan before issuing tool actions.

Why it matters here:

- it improves first-pass query quality,
- it is good at deciding subtopics, time windows, source preferences, and language,
- it maps cleanly to current task parameters such as `query_terms`, `days_back`, `max_items`, `provider`, `language`, and `source_library item_key`.

Recommendation:

- adopt this now as the `search brief` stage.

### 3.2 Interleaved reasoning-action strategies

Representative source:

- `ReAct`: [https://arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)

Key idea:

- alternate reasoning, tool action, observation, and updated reasoning.

Why it matters here:

- search is not a one-shot action,
- good search quality often requires changing parameters after observing initial results,
- this fits the existing `search.market` and `source_library` dual-path runtime.

Recommendation:

- adopt the ReAct loop structure, but do not expose arbitrary uncontrolled retries.
- wrap it in explicit stop conditions and bounded retry count.

### 3.3 Branching search strategies

Representative source:

- `Tree of Thoughts`: [https://arxiv.org/abs/2305.10601](https://arxiv.org/abs/2305.10601)

Key idea:

- explore multiple reasoning branches, score them, and continue from better branches.

Why it matters here:

- some research requests benefit from testing multiple search strategies:
  - broad recall,
  - high-precision entity search,
  - source-library-first,
  - recency-first.

Recommendation:

- do not make this the default path.
- use a reduced 2-to-3 branch version only for high-value, ambiguous, or cross-sector research tasks.

### 3.4 Retrieval-quality critic strategies

Representative sources:

- `Reflexion`: [https://arxiv.org/abs/2303.11366](https://arxiv.org/abs/2303.11366)
- `Self-RAG`: [https://arxiv.org/abs/2310.11511](https://arxiv.org/abs/2310.11511)
- `CRAG`: [https://arxiv.org/abs/2401.15884](https://arxiv.org/abs/2401.15884)
- `Probing-RAG`: [https://arxiv.org/abs/2410.13339](https://arxiv.org/abs/2410.13339)

Key idea:

- do not blindly trust the first retrieval pass,
- assess retrieval quality,
- if quality is insufficient, trigger a corrective action.

Why it matters here:

- this directly addresses the question “did the current search parameters work well enough?”
- it is the most natural way to decide whether to:
  - expand query terms,
  - narrow query scope,
  - change time window,
  - switch provider,
  - attach or replace `source_library` tasks.

Recommendation:

- implement a light `CRAG-lite` variant now.
- use simple runtime metrics plus LLM critique, not a large learned gating system yet.

### 3.5 RL-trained search policies

Representative source:

- `Search-R1`: [https://arxiv.org/abs/2503.09516](https://arxiv.org/abs/2503.09516)

Key idea:

- train the model to learn when and how to search during reasoning, instead of only prompting it.

Why it matters here:

- it is the strongest long-term answer to “can the agent learn to design better search parameters over time?”

Why it should be deferred:

- reward design is non-trivial,
- trajectory quality requirements are high,
- the current system can still gain a lot from prompt-time and inference-time policy improvements first.

Recommendation:

- keep this as a later program, not the immediate implementation plan.

### 3.6 Deep-research systems

Representative sources:

- `WebThinker`: [https://arxiv.org/abs/2504.21776](https://arxiv.org/abs/2504.21776)
- `OpenAI Deep Research System Card`: [https://openai.com/index/deep-research-system-card/](https://openai.com/index/deep-research-system-card/)

Key idea:

- long-horizon research agents that search, browse, extract, verify, and draft in one loop.

Why it matters here:

- it shows the likely end-state architecture for project-level research automation.

Recommendation:

- treat this as long-term north star, not phase-next implementation.

## 4. Selected Architecture for This Project

Selected stack:

1. `Plan-and-Solve` style `search brief`,
2. `ReAct` style observation-driven parameter revision,
3. `CRAG-lite` style critic and retry gating.

This is the recommended near-term architecture because it fits the current codebase shape:

- `agent_loop` already performs task planning and autonomous source-library mounting,
- `task_contract` already centralizes the executable task surface,
- `search.market` and `source_library` already provide enough parameter surface for a second-pass search rewrite loop.

## 5. Proposed Runtime Additions

### 5.1 New stage: `search_brief`

Insert a pre-execution stage before the task list is finalized.

Input:

- raw user goal,
- planner draft tasks,
- optional project context,
- optional known source hints.

Output shape:

```json
{
  "intent": "research_brief",
  "goal": "Find commercial products and companies in intelligent terminal market",
  "coverage_axes": ["products", "companies", "recent movement"],
  "time_strategy": {"mode": "recent", "days_back": 30},
  "search_strategies": [
    {"label": "broad", "query_terms": ["智能终端 商业产品 公司"]},
    {"label": "precision", "query_terms": ["智能终端 产品 厂商 融资 发布"]}
  ],
  "source_preferences": {
    "attach_source_library": true,
    "candidate_items": ["ai_terminal.weekly", "robotics.market_watch"]
  },
  "stop_conditions": {
    "min_entity_count": 8,
    "min_source_domains": 4,
    "max_search_rounds": 2
  }
}
```

Purpose:

- make search strategy explicit before execution,
- expose time, recall/precision bias, and source decisions as first-class runtime state,
- create a stable artifact that critic and retry stages can reference.

### 5.2 New stage: `search_critic`

Insert a post-search evaluation stage after each search round.

Input:

- search brief,
- task execution results,
- top entities / domains / snippets / source-library outputs,
- user goal.

Output shape:

```json
{
  "score": 0.62,
  "coverage": {
    "entity_coverage": 0.55,
    "source_diversity": 0.72,
    "freshness_fit": 0.80,
    "goal_alignment": 0.60,
    "novelty_gain": 0.35
  },
  "diagnosis": [
    "results are too broad and product/company distinction is weak",
    "source diversity is acceptable but entity coverage is incomplete"
  ],
  "next_action": "retry_with_precision_query",
  "rewrite": {
    "query_terms": ["智能终端 产品 公司 厂商 发布 融资"],
    "days_back": 45,
    "source_library": ["ai_terminal.weekly"]
  }
}
```

Purpose:

- make search quality measurable,
- allow bounded correction instead of silent low-quality completion.

### 5.3 New policy: bounded `retry / pivot`

Policy rules:

1. maximum retry rounds: `2`
2. maximum branch count for complex tasks: `3`
3. no unbounded self-looping
4. each retry must cite a concrete failure reason from critic output
5. retry action types must be finite and typed

Allowed corrective actions:

- `expand_query_terms`
- `narrow_query_terms`
- `shift_time_window`
- `change_provider`
- `attach_source_library`
- `replace_source_library`
- `stop`

This prevents the agent from turning into an unconstrained web loop.

## 6. Implementation Mapping to Current Codebase

### 6.1 `agent_loop`

Primary file:

- `main/backend/app/services/agent_batch/agent_loop.py`

Expected changes:

1. add a `search_brief` generation step before final normalized tasks are emitted,
2. preserve the `search_brief` artifact on the job state or stage events,
3. add a critic-evaluation step after the first execution round,
4. if critic score is below threshold and retry budget remains, request a bounded second-round task rewrite.

### 6.2 `task_contract`

Primary file:

- `main/backend/app/services/agent_batch/task_contract.py`

Expected changes:

1. define `search_strategy` and `critic_action` schemas,
2. define allowed retry mutations per channel,
3. define which top-level parameters are rewrite-eligible:
   - `query_terms`
   - `days_back`
   - `max_items`
   - `provider`
   - `language`
   - `source_mode`
   - `item_key` replacement set

### 6.3 `agent_batch`

Primary file:

- `main/backend/app/api/agent_batch.py`

Expected changes:

1. accept a new job-mode flag for bounded iterative search,
2. store retry state and critic diagnostics in item/job metadata,
3. keep approval and lane policy unchanged unless policy explicitly requires change.

### 6.4 observability

Expected new event types:

- `search_brief.created`
- `search_round.completed`
- `search_critic.scored`
- `search_retry.scheduled`
- `search_retry.skipped`
- `search_stop.completed`

These events are required if future RL or offline policy learning is ever attempted.

## 7. Minimal Evaluation Plan

### 7.1 Offline validation set

Build a small fixed benchmark of research-style prompts across categories:

1. market landscape
2. company watchlist
3. product scan
4. investment / financing scan
5. policy or standards tracking

For each prompt, measure:

- entity coverage,
- source diversity,
- freshness fit,
- duplicate ratio,
- retry usefulness,
- final report usefulness judged by rubric.

### 7.2 Online gating metrics

Minimum go/no-go metrics:

- critic-triggered retry rate,
- retry success uplift,
- average search rounds per task,
- average latency increase,
- source-library attachment precision,
- false-positive retry rate.

### 7.3 Acceptance threshold

Phase-next should only ship by default if:

1. one-retry uplift is positive on benchmark,
2. latency remains within acceptable operational budget,
3. false-positive retry rate stays controlled,
4. source-library auto-mount precision does not regress.

## 8. Delivery Phases

### P0

- add `search_brief` artifact generation,
- no retry yet,
- use it only for explainability and observability.

### P1

- add `search_critic` scoring,
- run in observe-only mode,
- record proposed retry action without executing it.

### P2

- enable bounded automatic retry for a subset of tasks,
- cap to one extra round by default.

### P3

- optionally enable reduced branching for complex tasks,
- only for selected high-value research flows.

### P4

- consider policy learning / RL after enough high-quality traces exist.

## 9. Risks

### 9.1 Over-agentization

If every task gets multi-round search, the system will become too slow and expensive.

Mitigation:

- keep retry budget explicit,
- gate branching to complex tasks only.

### 9.2 Unclear critic signal

If critic scoring is too subjective, retries will be noisy.

Mitigation:

- combine rubric metrics with LLM judgment,
- log failure reasons and review drift regularly.

### 9.3 Query churn without information gain

The agent may rewrite queries without improving output quality.

Mitigation:

- require `novelty_gain` and `goal_alignment` checks,
- stop early when critic predicts low marginal gain.

## 10. Final Recommendation

Proceed with:

1. `search brief` implementation,
2. observe-only `critic`,
3. one-round bounded retry,
4. later optional reduced branching.

Do not proceed yet with:

- large-scale branching by default,
- RL-trained search policy,
- deep-research-style fully autonomous browsing loops.

This gives the project a meaningful increase in search intelligence while preserving the current contract-governed runtime discipline.
