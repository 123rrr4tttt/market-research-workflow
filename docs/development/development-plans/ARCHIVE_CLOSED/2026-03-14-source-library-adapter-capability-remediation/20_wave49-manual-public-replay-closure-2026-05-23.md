# Wave49 Manual Public Replay Closure

Date: 2026-05-23 PST
Topic: `2026-03-14-source-library-adapter-capability-remediation`

## Decision

Status: `closed`.

The remaining adapter-capability blocker was the absence of a controlled full
45-site `demo_proj` public replay after the parser-profile, fallback,
taxonomy, review-queue, and deterministic review-batch gates had landed. That
blocker is now resolved by the real opt-in replay artifact:

```text
development/latest-dev-docs/automation-runs/source-library-replay-scaleout/2026-05-22/output.public.json
```

The replay satisfies the original `AT-AC-10` acceptance: it reran the real
historical `handler.cluster.search_template` site-entry set and produced a
per-site outcome table that distinguishes fetch/transport blockers,
anti-bot-or-transport blockers, empty/dynamic-source outcomes, policy skips,
and term-fallback relevance-review candidates.

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
| `candidate_ready_with_term_fallback` | 30 | Adapter reaches public pages and emits candidates; rows remain review evidence, not clean-source promotion. |
| `anti_bot_or_transport_blocked` | 4 | Public-site or network blocker classified per target. |
| `empty_public_result` | 4 | Empty or dynamic-source result classified per target. |
| `transport_blocked` | 2 | Public-network blocker classified per target. |
| `skipped_policy_disabled_platform_entry` | 5 | Expected policy skip for platform/API-required targets. |

## Boundary

This closes the adapter capability remediation topic. It does not claim that
all term-fallback candidates are clean source-library corpus entries, and it
does not close the broader three-lane, search-chain, or ingest-migration
topics. Those topics still own completed human review, live source collection,
governance mutation readback, or live ingest migration where their own
acceptance criteria require it.

## Validation

Commands run from repo root:

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_source_library_public_replay_a5_gate.py --repo-root .
```

Observed gate result:

```text
a5_status=full_public_replay_reviewed_closed
external_blocker.status=resolved
full_public_replay.status=real_evidence_present_review_required
full_public_replay.public_targets_attempted=40
validation.passed=true
```
