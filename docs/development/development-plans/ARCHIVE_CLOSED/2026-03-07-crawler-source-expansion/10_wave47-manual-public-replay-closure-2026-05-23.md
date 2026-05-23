# Wave47 Manual Public Replay Closure

Date: 2026-05-23 PST
Topic: `2026-03-07-crawler-source-expansion`

## Decision

A5 status: `closed`.

Topic closure decision: `closed`.

The former external blocker was the absence of a controlled full 45-site public replay. That blocker is now resolved by a real opt-in replay artifact at:

```text
development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json
```

The public replay gate reads the artifact as `real_evidence_present_review_required`. This note is the manual review record that converts that gate result into topic closure.

## Replay Readback

| Field | Value |
| --- | --- |
| `allow_public_network` | `true` |
| historical targets | `45` |
| enabled public targets attempted | `40` |
| platform/API policy-skipped targets | `5` |
| operator-gate public-network skips | `0` |
| validation | `passed` |
| `live_evidence_sufficient` | `true` |

Status counts from `output.public.json`:

| Status | Count | Closure interpretation |
| --- | ---: | --- |
| `candidate_ready_with_term_fallback` | 30 | Relevance-review evidence; not promoted as clean source-corpus closure. |
| `anti_bot_or_transport_blocked` | 4 | Public-site/network blocker classified per target. |
| `empty_public_result` | 4 | Empty or dynamic-source outcome classified per target. |
| `transport_blocked` | 2 | Public-network blocker classified per target. |
| `skipped_policy_disabled_platform_entry` | 5 | Expected policy skip for platform/API-required targets. |

## Manual Review

The original A5 condition was not "all public sites must produce clean candidates". It was to run the full historical public replay and record per-target outcomes instead of relying on a deterministic no-network placeholder.

The replay now attempted all 40 enabled public targets and preserved the five platform/API entries as policy skips. The remaining public-site outcomes are explicitly classified in the artifact; they are not repo-local implementation blockers. `candidate_ready_with_term_fallback` remains a review bucket, and those rows must not be counted as clean directed-source onboarding without later relevance review.

This is sufficient to close the crawler source expansion topic because the missing external proof is now present and reviewed. Downstream source-quality promotion remains owned by source-library relevance review topics, not by this target.

## Validation

Commands run from repo root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/source_library_replay_scaleout.py --allow-public-network --output development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json --log-output development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/logs/output.public.log
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_crawler_public_replay_gate.py --repo-root . --output /tmp/wave47-crawler-public-replay-gate-check.json
```

Observed gate result:

```text
overall_status=deterministic_artifacts_valid_live_public_replay_evidence_present_review_required
live_public_replay.status=real_evidence_present_review_required
live_public_replay.public_targets_attempted=40
live_public_replay.policy_skipped_status_count=5
live_public_replay.operator_gate_skip_count=0
```
