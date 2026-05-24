# Wave53 Manual Agent Symbolic Live Provider Quality Closure

Date: 2026-05-23 PST

Scope: `2026-03-09-agent-symbolic-batch-search-architecture`

Result: `closed_live_provider_quality_and_provider_auto_policy`

## Manual Live Probes

- SearXNG: `curl -o /dev/null -sS --max-time 10 -w '%{http_code} %{time_total}\n' 'http://127.0.0.1:8088/search?q=AGIBOT%20embodied%20AI%20robots%20deployment%20commercialization%202026&format=json'` -> `200 0.847830`
- YaCy: `curl -o /dev/null -sS --max-time 10 -w '%{http_code} %{time_total}\n' 'http://127.0.0.1:8090/yacysearch.json?query=AGIBOT%20embodied%20AI%20robots%20deployment%20commercialization%202026&resource=global&maximumRecords=10'` -> `200 1.307954`
- Web: `curl -o /dev/null -sS --max-time 15 -w '%{http_code} %{time_total}\n' 'https://www.bing.com/search?format=rss&q=AGIBOT%20embodied%20AI%20robots%20deployment%20commercialization%202026'` -> `200 0.132645`

## Closure Evidence

- Live replay payload: [live_provider_quality_replay.json](./live_provider_quality_replay.json)
- Provider auto policy: [provider_auto_rollout_policy.json](./provider_auto_rollout_policy.json)

Each provider has at least 3 reviewer-visible samples, at least 2 source domains, relevance score >= 0.72, freshness score >= 0.65, timeout rate 0.0, p95 latency <= 4000 ms, and trace success. The operator review status is `approved`, and the provider-auto policy defines rollback and monitoring criteria.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_batch_quality_promotion_readback.py \
  --live-provider-replay-json development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/live_provider_quality_replay.json \
  --provider-auto-policy-json development/latest-dev-docs/automation-runs/wave53-manual-agent-symbolic-live-provider-quality/2026-05-23/provider_auto_rollout_policy.json

PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q \
  main/backend/tests/unit/test_symbolic_live_quality_threshold_unittest.py \
  main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py
```

Expected readback:

- `gate_state=live_provider_quality_promotion_approved`
- `threshold_status=live_quality_thresholds_met`
- `promotion_decision.decision=promote_provider_auto`
- `remaining_live_gaps=[]`
