# Wave20 Evidence: Agent Batch Quality Promotion Readback

Date: 2026-05-22 (PST)
Status: `partial / provider_independent_quality_promotion_held_live_gap_open`
Scope: provider-independent quality promotion/readback for Agent Symbolic Batch Search.

## What This Advances

This worker adds a deterministic promotion/readback gate on top of the existing search brief, critic, bounded retry, fixture quality, provider readiness, and live-threshold contracts.

- Fixture search brief readback is recorded from `robotics-source-gap`.
- Critic score readback binds the decision source to `search_critic.score` with score `0.66` and threshold `0.72`.
- Bounded retry readback verifies budget `1`, max rounds `1`, one retry-allowed trace, and one retry-blocked trace.
- Quality threshold readback preserves `threshold_contract_ready_live_replay_gap_open`.
- Promotion decision readback validates `hold_provider_auto_promotion` with digest `adfa1129333c9e86`.

The gate rejects caller-supplied provider-auto promotion claims. Passing this gate does not close live provider quality and does not promote SearXNG, YaCy, web, or `provider=auto`.

## New Gate

- Contract helper: `main/backend/app/services/agent_batch/search_quality_replay.py`
- Policy schema: `main/backend/app/services/agent_batch/task_contract.py`
- Checker: `main/backend/scripts/check_agent_batch_quality_promotion_readback.py`
- Unit gate: `main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py`
- Evidence: `development/latest-dev-docs/automation-runs/wave20-agent-batch-quality-promotion/2026-05-22/quality_promotion_readback.json`

Validated contract output:

```json
{
  "contract_version": "agent-symbolic-batch-search.wave20.quality_promotion_readback.v1",
  "scope": "provider_independent_agent_batch_quality_promotion_readback_no_network",
  "status": "passed",
  "gate_state": "provider_independent_quality_promotion_held_live_gap_open",
  "promotion_decision": "hold_provider_auto_promotion"
}
```

## Evidence Matrix

| Requirement | Evidence | Result |
|---|---|---|
| Fixture search brief | Readback includes `robotics-source-gap`, goal, coverage axes, `days_back=30`, and `robotics.market_watch` candidate item | passed |
| Critic score | Readback pins score `0.66`, threshold `0.72`, `next_action=retry_with_precision_query`, and source `search_critic.score` | passed |
| Bounded retry | Readback validates retry budget `1`, max rounds `1`, retry allowed `1`, retry blocked `1`, and observational replay score | passed |
| Quality threshold | Readback keeps `threshold_contract_ready_live_replay_gap_open`, `live_provider_replay_closed=false`, and `quality_claim_allowed=false` | passed |
| Promotion decision readback | Decision `hold_provider_auto_promotion` is read back with matching digest `adfa1129333c9e86` | passed |
| Input promotion claim rejection | Caller-supplied `promote_provider_auto` remains rejected by computed gate output | passed |

## Remaining Gaps

1. `live_provider_replay_not_run`: no real SearXNG, YaCy, browser, or external web replay is attached.
2. `searxng_live_provider_replay_not_attached`: SearXNG has no threshold-evaluated live replay row.
3. `yacy_live_provider_replay_not_attached`: YaCy has no threshold-evaluated live replay row.
4. `web_live_provider_replay_not_attached`: browser/external-web replay has no threshold-evaluated live replay row.
5. `operator_review_not_approved`: reviewer-visible samples and operator approval remain required.
6. `provider_auto_promotion_readback_hold`: provider-auto promotion remains held until live quality and operator policy gates pass.

## Verification Commands

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_batch_quality_promotion_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py
```
