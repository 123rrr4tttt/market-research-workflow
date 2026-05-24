# Wave23 External-Blocked Decision: Agent Symbolic Batch Search Architecture

Date: 2026-05-23
Result: `archive_external_blocked_candidate`
Repo-local blocker: `no`

## Decision

This topic is a directory-level `ARCHIVE_EXTERNAL_BLOCKED` candidate.

The current `CURRENT_DEV` status is still `partial`, but the remaining blocker is not a repo-local implementation/checker blocker. The repo-local deterministic and provider-independent gates have already landed for:

- Wave9 search brief / critic / bounded retry contract.
- Wave11 symbolic search quality replay boundary.
- Wave13 provider-quality readiness gate.
- Wave15 live quality threshold contract.
- Wave18 provider-independent symbolic quality regression evaluator.
- Wave20 provider-independent quality promotion/readback.

The remaining closure gap is the live provider quality path: SearXNG / YaCy / web replay rows are not attached, threshold-evaluated live replay has not run, operator review is not approved, and provider-auto promotion remains held.

## Evidence Reviewed

Topic-local markdown reviewed:

- `README.md`
- `01_agent-symbolic-batch-search-plan-2026-03-09.md`
- `02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md`
- `03_atomic-task-library-investigation-map-2026-03-10.md`
- `04_parallel-execution-playbook-spark-codex-2026-03-10.md`
- `07_agent-loop-kernel-architecture-and-planner-governance-2026-03-11.md`
- `08_backend-ai-agent-runtime-architecture-2026-03-11.md`
- `09_backend-full-skillization-best-practices-and-implementation-plan-2026-03-11.md`
- `10_backend-mcp-vs-skill-layering-and-rollout-2026-03-14.md`
- `11_agent-exposed-task-contract-completeness-audit-2026-03-14.md`
- `12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md`
- `13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md`
- `14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md`
- `15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md`
- `16_wave9-agent-symbolic-batch-search-contract-evidence-2026-05-22.md`
- `17_wave11-symbolic-search-quality-replay-evidence-2026-05-22.md`
- `18_wave13-symbolic-provider-quality-readiness-evidence-2026-05-22.md`
- `19_wave15-symbolic-live-quality-threshold-2026-05-22.md`
- `20_wave18-symbolic-quality-regression-evaluator-2026-05-22.md`
- `21_wave20-agent-batch-quality-promotion-readback-2026-05-22.md`

Additional inputs reviewed:

- `../INDEX.md`: topic is marked `partial` with Wave9/Wave11/Wave13/Wave15/Wave18/Wave20 evidence and live provider quality still open.
- `../STATUS_AUDIT_2026-04-07.md`: same status pattern; repo-local evidence is present while live provider quality remains unclosed.
- `../../../automation-runs/wave20-agent-batch-quality-promotion/2026-05-22/README.md`
- `../../../automation-runs/wave20-agent-batch-quality-promotion/2026-05-22/quality_promotion_readback.json`
- Related checkers/tests under `main/backend/scripts/check_agent_symbolic_search_quality_replay.py`, `main/backend/scripts/check_agent_symbolic_provider_quality_readiness.py`, `main/backend/scripts/check_symbolic_live_quality_threshold.py`, `main/backend/scripts/check_symbolic_quality_regression_evaluator.py`, `main/backend/scripts/check_agent_batch_quality_promotion_readback.py`, and matching unit tests.

## Archive Rationale

The topic should not be retained in `CURRENT_DEV` for additional repo-local work because the latest evidence preserves all known repo-local quality gates and rejects false closure claims:

- Wave11 closes deterministic replay only and explicitly keeps live provider quality out of scope.
- Wave13 converts live-provider quality into a readiness boundary and keeps unsupported live claims rejected.
- Wave15 defines the live quality threshold contract, while requiring a separate `live_provider_quality_replay`.
- Wave18 combines the prior provider-independent gates and still emits `live_provider_quality_open=true`.
- Wave20 validates quality promotion/readback and still decides `hold_provider_auto_promotion`.

The open work now requires external/live evidence rather than local code closure:

- `live_provider_quality_replay`
- `all_provider_threshold_rows_passed`
- `operator_review_approved`
- `provider_auto_rollout_policy_approved`

## Remaining External Blockers

The remaining blocker set is external/live-provider gated:

1. `live_provider_replay_not_run`
2. `searxng_live_provider_replay_not_attached`
3. `yacy_live_provider_replay_not_attached`
4. `web_live_provider_replay_not_attached`
5. `operator_review_not_approved`
6. `provider_auto_promotion_readback_hold`

No repo-local blocker was found that would require keeping this directory in `CURRENT_DEV`.

## Verification

Minimum gate selected: related checker/pytest for Wave20 quality promotion/readback.

Commands run:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_agent_batch_quality_promotion_readback.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_agent_batch_quality_promotion_readback_unittest.py
```

Verification status: `passed`.

- Checker result: `status=passed`, `gate_state=provider_independent_quality_promotion_held_live_gap_open`, `promotion_decision=hold_provider_auto_promotion`.
- Pytest result: `2 passed in 0.03s`.

Scope guard: this Wave23 pass only adds this topic-local decision file. It does not edit shared indexes, README, `MERGED_OVERVIEW`, and does not move the directory.
