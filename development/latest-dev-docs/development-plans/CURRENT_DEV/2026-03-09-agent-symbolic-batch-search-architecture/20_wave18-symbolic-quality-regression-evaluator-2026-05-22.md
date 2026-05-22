# Wave18 Evidence: Symbolic Quality Regression Evaluator

Date: 2026-05-22 (PST)
Status: `partial / provider_independent_quality_regression_passed_live_provider_quality_open`
Scope: provider-independent deterministic quality regression for Agent Symbolic Batch Search.

## What This Advances

This worker adds a deterministic evaluator that combines the prior symbolic-search contracts without claiming live provider closure:

- Wave9 input contract is still required through `search_brief`, `search_critic`, and bounded `retry_action` schemas.
- Wave11 fixture replay quality is evaluated through `score_quality_benchmark_replay` and a fixture threshold row.
- Wave13 provider-quality readiness remains the source of unsupported live-provider claims and live gap rows.
- Wave15 live quality threshold status is read back and must remain `threshold_contract_ready_live_replay_gap_open`.
- The evaluator emits `live_provider_quality_open=true`, `quality_claim_allowed=false`, and `live_provider_quality_closed_by_evaluator=false`.

This does not close live provider quality. The checker does not start SearXNG, YaCy, browser, or external web providers, and it rejects caller-supplied live quality closure claims unless a separate live replay threshold gate owns that evidence.

## New Gate

- Contract helper: `main/backend/app/services/agent_batch/search_quality_replay.py`
- Checker: `main/backend/scripts/check_symbolic_quality_regression_evaluator.py`
- Unit gate: `main/backend/tests/unit/test_symbolic_quality_regression_evaluator_unittest.py`

Validated contract output:

```json
{
  "contract_version": "agent-symbolic-batch-search.wave18.quality_regression.v1",
  "scope": "provider_independent_symbolic_quality_regression_no_network",
  "status": "passed",
  "threshold_status": "threshold_contract_ready_live_replay_gap_open",
  "live_provider_quality_open": true
}
```

## Evidence Matrix

| Requirement | Evidence | Result |
|---|---|---|
| Fixture result quality threshold | Evaluator requires `case_count=2`, positive `average_uplift=0.15`, `false_positive_retry_rate=0.0`, and fixture quality claim blocked | passed |
| Critic / bounded retry trace | Evaluator records one retry-allowed trace and one retry-blocked trace; replay score remains observational and cannot override `search_critic` | passed |
| Wave15 threshold status | Evaluator reads the live threshold contract and requires `threshold_contract_ready_live_replay_gap_open` | passed |
| Live provider gap preserved | Evaluator emits `live_provider_quality_open=true`, `quality_claim_allowed=false`, and remaining gaps for live replay, provider rows, and operator review | passed |
| Input claim rejection | Checker simulates caller-supplied `quality_claim_allowed=true` and `live_provider_replay_closed=true`; evaluator keeps the live gap open | passed |
| Shared-index boundary | Worker evidence is topic-local only; shared navigation indexes are intentionally untouched | passed |

## Remaining Gaps Before Overall Topic Closure

1. `live_provider_replay_not_run`: real SearXNG / YaCy / web provider replay is not attached to this gate.
2. `searxng_live_provider_replay_not_attached`: SearXNG has no threshold-evaluated live replay row.
3. `yacy_live_provider_replay_not_attached`: YaCy has no threshold-evaluated live replay row.
4. `web_live_provider_replay_not_attached`: browser/external-web replay has no threshold-evaluated live replay row.
5. `operator_review_not_approved`: reviewer-visible samples and operator approval are still required before live quality closure.
6. `global_topic_closure_requires_index_audit`: this worker does not edit shared CURRENT_DEV indexes.

## Verification Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_symbolic_quality_regression_evaluator.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_symbolic_quality_regression_evaluator_unittest.py
python3 scripts/check_current_dev_wave18_plan.py
git diff --check
```
