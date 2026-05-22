# Wave13 Evidence: Symbolic Provider Quality Readiness Boundary

Date: 2026-05-22 (PST)
Status: `partial / provider_quality_readiness_gate_closed_live_gap_open`
Scope: deterministic symbolic search provider-quality readiness contract, fixture quality summary, unsupported live-provider claims, and remaining live gaps.

## What This Closes

This worker adds a repo-controlled readiness gate for the live-provider blocker left after Wave11 fixture replay:

- fixture replay quality is recorded as a required readiness input;
- live-provider quality claims remain unsupported unless a separate live replay proves result quality, latency, timeout, trace, and review thresholds;
- provider auto-promotion remains blocked;
- remaining live gaps are emitted as machine-readable gate output instead of being implied by prose.

This does not close live provider quality. The gate is deterministic and does not start SearXNG, YaCy, browser, or external web providers.

## New Gate

- Contract helper: `main/backend/app/services/agent_batch/search_quality_replay.py`
- Contract schema exposure: `main/backend/app/services/agent_batch/task_contract.py`
- Checker: `main/backend/scripts/check_agent_symbolic_provider_quality_readiness.py`
- Unit gates:
  - `main/backend/tests/unit/test_agent_batch_search_quality_replay_unittest.py`
  - `main/backend/tests/unit/test_agent_symbolic_provider_quality_readiness_unittest.py`

Validated contract output:

```json
{
  "contract_version": "agent-symbolic-batch-search.wave13.provider_quality_readiness.v1",
  "scope": "symbolic_search_provider_quality_readiness_no_network",
  "status": "passed",
  "closure_claim": "fixture_quality_recorded_live_provider_quality_not_closed"
}
```

## Evidence Matrix

| Requirement | Evidence | Result |
|---|---|---|
| Fixture quality recorded | Checker requires `fixture_quality.status=passed`, positive `average_uplift`, zero `false_positive_retry_rate`, and `quality_claim_allowed=false` | passed |
| Unsupported live-provider claims | Checker requires unsupported claims for fixture-as-live quality, provider availability as quality, provider auto-promotion, and live retry uplift closure | passed |
| Remaining live gaps | Checker emits provider-specific live gaps plus live result-quality threshold, live retry uplift replay, and operator policy gaps | passed |
| Input claim rejection | Checker simulates a caller-supplied live quality claim and verifies it is recorded but rejected by the symbolic readiness gate | passed |
| Shared-index boundary | Worker evidence is topic-local only; shared navigation indexes are intentionally untouched | passed |

## Remaining Gaps Before Overall Topic Closure

1. `searxng_live_provider_not_ready`: no symbolic provider-quality live replay is attached to this gate.
2. `yacy_live_provider_not_ready`: no symbolic provider-quality live replay is attached to this gate.
3. `web_live_provider_not_ready`: no browser/external-web symbolic quality replay is attached to this gate.
4. `live_result_quality_threshold_not_defined`: live thresholds for result count, source diversity, relevance, freshness, latency, and timeout still need a separate gate.
5. `live_retry_uplift_replay_not_run`: deterministic uplift is fixture-only and cannot prove live provider ranking quality.
6. `provider_auto_operator_policy_not_approved`: provider auto-routing still needs operator approval, rollback, and review boundaries.

## Verification Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_symbolic_provider_quality_readiness.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_batch_search_quality_replay_unittest.py main/backend/tests/unit/test_agent_symbolic_provider_quality_readiness_unittest.py
python3 scripts/check_current_dev_wave13_plan.py
git diff --check
```
