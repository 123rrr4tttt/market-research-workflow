# Wave9 Evidence: Agent Symbolic Batch Search Contract

Date: 2026-05-22 (PST)  
Status: `partial / deterministic_minimal_loop_closed`  
Scope: `agent_batch` exposed task contract, search brief, critic, and bounded retry policy.

## What This Closes

This evidence closes the narrow runtime-contract gap identified by the CURRENT_DEV audit:

- `agent_batch` exposes callable `search.market` and `source_library` task contracts through the task manifest.
- `search_brief` is generated as a structured artifact with coverage axes, time strategy, search strategies, source preferences, and stop conditions.
- `search_critic` produces score, coverage metrics, diagnosis, reason codes, and a finite next action.
- bounded retry remains one extra round by default and validates retry payloads through fail-closed rewrite rules.
- retry can rewrite `search.market` query terms and can attach one `source_library` task when the critic identifies a source-backed coverage gap.

## New Gate

- Checker: `main/backend/scripts/check_agent_symbolic_batch_search_contract.py`
- Unit gate: `main/backend/tests/unit/test_agent_symbolic_batch_search_contract_unittest.py`

The checker is deterministic and intentionally does not start network providers, containers, workers, or source-library live probes.

Validated contract output:

```json
{
  "contract_version": "agent-symbolic-batch-search.wave9.v1",
  "scope": "deterministic_no_network_agent_batch_search_brief_critic_retry",
  "status": "passed",
  "closure_claim": "minimal_runtime_loop_closed_not_global_topic"
}
```

## Evidence Matrix

| Requirement | Evidence | Result |
|---|---|---|
| Agent-exposed task contract | `build_agent_batch_task_manifest()` exposes `search.market` and `source_library`; search policy schemas expose `search_brief`, `search_critic`, `retry_action`, defaults, and event names | passed |
| Fail-closed retry governance | checker rejects `search.market` retry payload that tries to rewrite `item_key` | passed |
| Search brief artifact | checker replays an in-memory NL loop and asserts required brief keys and loop stage | passed |
| Critic artifact | checker asserts critic score, coverage, diagnosis, reason codes, and next action | passed |
| Bounded precision retry | checker proves exactly two submit rounds, round-scoped retry idempotency key, and changed `query_terms` | passed |
| Source-library retry | checker proves source-gap critic can attach one `source_library` task with preserved `max_items` | passed |

## Remaining Blockers Before Overall Topic Closure

The topic should remain `partial` rather than globally closed until these are handled by a supervisor/index wave:

1. `live_provider_and_source_quality_not_replayed`: this gate does not start SearXNG/YaCy/web providers or perform live source-library network probes.
2. `benchmark_uplift_not_proven`: AT-SB-08 benchmark/go-no-go rubric is not replayed, so retry usefulness and false-positive retry rate are not proven.
3. `global_topic_closure_requires_index_audit`: this worker only adds topic-local evidence and does not edit shared CURRENT_DEV indexes.

## Verification Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_symbolic_batch_search_contract.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_symbolic_batch_search_contract_unittest.py main/backend/tests/unit/test_agent_batch_loop_unittest.py main/backend/tests/unit/test_agent_batch_planner_unittest.py
git diff --check
```
