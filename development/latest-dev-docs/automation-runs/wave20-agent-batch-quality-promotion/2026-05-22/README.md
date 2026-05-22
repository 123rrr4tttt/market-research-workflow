# Wave20 Agent Batch Quality Promotion Readback Evidence

Date: 2026-05-22 (PST)
Status: `passed / provider_independent_quality_promotion_held_live_gap_open`
Scope: provider-independent Agent Batch quality promotion/readback gate.

## Evidence

- `quality_promotion_readback.json`: checker output from `main/backend/scripts/check_agent_batch_quality_promotion_readback.py`.

## Readback Summary

| Field | Readback |
|---|---|
| fixture search brief | `robotics-source-gap`, coverage axes `products`, `companies`, `recent_movement` |
| critic score | `0.66`, source `search_critic.score`, threshold `0.72` |
| bounded retry | enabled, budget `1`, max rounds `1`, retry allowed `1`, retry blocked `1` |
| quality threshold | `threshold_contract_ready_live_replay_gap_open` |
| promotion decision | `hold_provider_auto_promotion` |
| promotion decision digest | `adfa1129333c9e86` |

## Boundary

This evidence validates fixture quality promotion/readback only. It does not start live providers, does not close live provider quality, and does not allow provider-auto promotion.

Remaining open gaps include `live_provider_replay_not_run`, provider-specific live replay attachment gaps, `operator_review_not_approved`, and `provider_auto_promotion_readback_hold`.

## Verification

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_batch_quality_promotion_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py
```
