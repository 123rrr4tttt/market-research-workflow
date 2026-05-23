# Wave11 Evidence: Symbolic Search Quality Replay Boundary

Date: 2026-05-22 (PST)
Status: `partial / deterministic_quality_replay_closed`
Scope: provider-quality replay boundary, source quality signals, critic retry boundary, and deterministic benchmark uplift for symbolic batch search.

## What This Closes

This worker closes the narrow deterministic slice left open by Wave9:

- source quality replay now has a frozen contract shape through `search_quality_replay`;
- replayed records emit explicit source quality signals: domain, channel, provider, provider trace state, axis hits, freshness, domain relevance, and per-record quality score;
- critic retry boundary remains governed by `search_critic.score`, retry budget, and typed next action, so replay scores are observational and do not silently authorize retries;
- source-gap retry can still bypass the numeric threshold only for the existing `source_backing_missing` boundary;
- deterministic fixture replay shows positive retry uplift while keeping false-positive retry rate visible.

This evidence does not close live provider quality. It does not start SearXNG, YaCy, browser, or external web providers.

## New Gate

- Contract helper: `main/backend/app/services/agent_batch/search_quality_replay.py`
- Contract schema exposure: `main/backend/app/services/agent_batch/task_contract.py`
- Checker: `main/backend/scripts/check_agent_symbolic_search_quality_replay.py`
- Unit gates:
  - `main/backend/tests/unit/test_agent_batch_search_quality_replay_unittest.py`
  - `main/backend/tests/unit/test_agent_symbolic_search_quality_replay_unittest.py`

Validated contract output:

```json
{
  "contract_version": "agent-symbolic-batch-search.wave11.quality_replay.v1",
  "scope": "provider_quality_replay_boundary_and_benchmark_uplift_no_network",
  "status": "passed",
  "closure_claim": "deterministic_quality_replay_closed_not_live_provider_quality"
}
```

## Evidence Matrix

| Requirement | Evidence | Result |
|---|---|---|
| Source quality signals | Checker validates per-record `source_quality_signals` with deterministic provider trace state and `provider_live_verified=false` | passed |
| Live-provider gap state | Replay output includes `live_provider_gap_state.status=not_run`, `providers_not_started=[searxng, yacy, web]`, and `quality_claim_allowed=false` | passed |
| Critic retry boundary | Checker proves `critic_stop` blocks retry even when replay score is lower, and source-gap threshold bypass remains explicit | passed |
| Benchmark uplift replay | Fixture benchmark reports `average_uplift=0.29` and `false_positive_retry_rate=0.0` | passed |
| Shared-index boundary | Worker evidence is topic-local only; shared navigation indexes are intentionally untouched | passed |

## Remaining Gaps Before Overall Topic Closure

1. `live_provider_quality_not_verified`: this gate intentionally does not start SearXNG, YaCy, browser, or external web providers.
2. `production_benchmark_requires_live_provider_replay`: uplift here is fixture replay only and cannot prove live-provider ranking quality.
3. `global_topic_closure_requires_index_audit`: this worker only adds topic-local evidence and does not edit shared CURRENT_DEV indexes.

## Verification Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_symbolic_search_quality_replay.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_batch_search_quality_replay_unittest.py main/backend/tests/unit/test_agent_symbolic_search_quality_replay_unittest.py main/backend/tests/unit/test_agent_batch_planner_unittest.py
python3 scripts/check_current_dev_wave11_plan.py
git diff --check
```
