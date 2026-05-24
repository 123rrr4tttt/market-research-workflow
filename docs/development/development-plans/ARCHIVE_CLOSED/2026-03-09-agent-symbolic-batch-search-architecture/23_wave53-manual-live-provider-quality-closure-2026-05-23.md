# Wave53 Manual Live Provider Quality Closure

Date: 2026-05-23 PST

Scope: `2026-03-09-agent-symbolic-batch-search-architecture`

Status: `closed`

## Decision

This target is closed.

The remaining Wave23 external blocker set has been resolved with a real live-provider replay and an explicit provider-auto rollout policy:

- SearXNG, YaCy, and Web live replay rows are attached.
- Each provider has at least 3 reviewer-visible samples and at least 2 source domains.
- Every provider row passes relevance, freshness, timeout, latency, review-sample, and trace thresholds.
- Operator review is `approved`.
- `provider=auto` promotion is approved only with rollback and daily monitoring criteria.

## Evidence

- Manual run record: [README](../../../../../development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/README.md)
- Live replay payload: [live_provider_quality_replay.json](../../../../../development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/live_provider_quality_replay.json)
- Provider-auto policy: [provider_auto_rollout_policy.json](../../../../../development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/provider_auto_rollout_policy.json)

Code and gate changes:

- `main/backend/app/services/agent_batch/search_quality_replay.py` now keeps the old provider-independent `hold_provider_auto_promotion` path for missing live evidence, and only promotes when `live_provider_quality_replay` passes thresholds and the rollout policy is approved.
- `main/backend/scripts/check_agent_batch_quality_promotion_readback.py` now accepts attached live replay and policy JSON for closure readback.
- `main/backend/tests/unit/test_symbolic_live_quality_threshold_unittest.py` and `main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py` cover both the default hold path and the live-closed promotion path.

## Readback

The live closure gate reports:

- `status=passed`
- `gate_state=live_provider_quality_promotion_approved`
- `threshold_status=live_quality_thresholds_met`
- `promotion_decision=promote_provider_auto`
- `remaining_live_gaps=[]`

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_batch_quality_promotion_readback.py --live-provider-replay-json development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/live_provider_quality_replay.json --provider-auto-policy-json development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/provider_auto_rollout_policy.json
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_symbolic_live_quality_threshold_unittest.py main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py
```

Result: passed.
