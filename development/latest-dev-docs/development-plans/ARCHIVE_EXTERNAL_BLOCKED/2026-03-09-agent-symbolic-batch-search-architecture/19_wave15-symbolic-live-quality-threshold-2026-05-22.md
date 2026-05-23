# Wave15 Evidence: Symbolic Live Quality Threshold

Date: 2026-05-22 (PST)
Status: `partial / live_quality_threshold_contract_ready_live_replay_gap_open`
Scope: repo-local live provider quality threshold contract for Agent Symbolic Batch Search.

## What This Closes

This worker adds a deterministic threshold gate for the live provider quality blocker left open by Wave11 and Wave13:

- live provider quality now has a frozen threshold shape: result count, source diversity, relevance, freshness, duplicate rate, timeout rate, p95 latency, trace success, and reviewer-visible samples;
- fixture replay uplift is explicitly carried forward as fixture evidence only, with `live_provider_quality_equivalent=false`;
- provider availability or caller-supplied quality claims are rejected unless a `live_provider_quality_replay` artifact passes the threshold contract;
- `provider=auto` promotion remains blocked by a separate operator rollout policy.

This does not close live provider quality. The checker does not start SearXNG, YaCy, browser, or external web providers, and the real provider replay remains open.

## New Gate

- Contract helper: `main/backend/app/services/agent_batch/search_quality_replay.py`
- Contract schema exposure: `main/backend/app/services/agent_batch/task_contract.py`
- Checker: `main/backend/scripts/check_symbolic_live_quality_threshold.py`
- Unit gate: `main/backend/tests/unit/test_symbolic_live_quality_threshold_unittest.py`

Validated contract output:

```json
{
  "contract_version": "agent-symbolic-batch-search.wave15.live_quality_threshold.v1",
  "scope": "symbolic_search_live_quality_threshold_no_network",
  "status": "passed",
  "threshold_status": "threshold_contract_ready_live_replay_gap_open",
  "live_provider_replay_closed": false,
  "quality_claim_allowed": false
}
```

## Evidence Matrix

| Requirement | Evidence | Result |
|---|---|---|
| Fixture uplift stays separate | Checker carries Wave11/Wave13 fixture quality with positive uplift but requires `quality_claim_allowed=false` and `live_provider_quality_equivalent=false` | passed |
| Live threshold shape is frozen | Contract requires provider rows for result count, source domains, relevance, freshness, duplicate rate, timeout rate, p95 latency, review samples, and trace success | passed |
| Provider replay remains open | Checker emits `live_provider_replay_not_run`, per-provider replay gaps, and `operator_review_not_approved` | passed |
| Input live claim is rejected | Checker simulates a caller-supplied live quality claim and verifies it is recorded but recomputed as `quality_claim_allowed=false` | passed |
| Shared-index boundary | Worker evidence is topic-local only; shared navigation indexes are intentionally untouched | passed |

## Remaining Gaps Before Overall Topic Closure

1. `live_provider_replay_not_run`: real SearXNG / YaCy / web provider replay is not attached to this gate.
2. `searxng_live_provider_replay_not_attached`: SearXNG has no threshold-evaluated live replay row.
3. `yacy_live_provider_replay_not_attached`: YaCy has no threshold-evaluated live replay row.
4. `web_live_provider_replay_not_attached`: browser/external-web replay has no threshold-evaluated live replay row.
5. `operator_review_not_approved`: reviewer-visible samples and operator approval are still required before live quality closure.

## Verification Commands

```bash
python3 scripts/check_current_dev_wave15_plan.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_symbolic_live_quality_threshold.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_symbolic_live_quality_threshold_unittest.py main/backend/tests/unit/test_agent_batch_search_quality_replay_unittest.py main/backend/tests/unit/test_agent_batch_planner_unittest.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
git diff --check
```
