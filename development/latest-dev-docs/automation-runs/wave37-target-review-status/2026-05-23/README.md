# Wave37 Target Review Status

Date: 2026-05-23 PST

## Result

This run makes the target-topic matrix directly express the four working states requested for development-plan governance:

- `unsealed`: active `CURRENT_DEV` work still counted as `partial`, `not_closed`, or `no_closure_claim`
- `sealed`: target topics whose repo-local work is closed, including `external_blocked` topics whose remaining condition is outside the repo
- `outdated`: retired target topics
- `needs_update`: target topics that remain in an archive but need a status/evidence refresh

Current output from `scripts/checkers/check_development_plans_status_matrix.py --root . --json`:

| Field | Value |
|---|---:|
| `unsealed_count` | 0 |
| `sealed_count` | 49 |
| `outdated_count` | 6 |
| `needs_update_count` | 6 |
| `external_blocked_count` | 29 |

Archive status remains unchanged:

| Archive status | Count |
|---|---:|
| `closed` | 26 |
| `external_blocked` | 29 |
| `retired` | 6 |
| `active_current` | 0 |

Review status now separates six `needs_update` topics from the archive status:

| Review status | Count |
|---|---:|
| `closed` | 20 |
| `external_blocked` | 29 |
| `retired` | 6 |
| `needs_update` | 6 |

## Needs-Update Topics

- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-02-ingest-chain-full-branch-map`
  Reason: true development target, but only compatibility-shim evidence remains and no reproducible closure test result is bound to the topic.
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan`
  Reason: Round6 is closed, but Round7 remains a draft without a matching closure record.
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan`
  Reason: Round6 is closed, but Round7 remains a draft without a matching closure record.
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-cd-r3-c-observability-minimal`
  Reason: test commands exist, but no current execution-result proof is bound to this target.
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排`
  Reason: folderization structure is closed, but old pending/status snapshots remain as topic-local refresh work.
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration`
  Reason: repo-local runtime boundary is documented, but worker/subagent runtime proof is explicitly split to successor work.

## Code Changes

`scripts/checkers/check_development_plans_status_matrix.py` now adds these JSON fields without removing legacy fields:

- `state_schema_version`
- `generated_at`
- `target_review_status_counts`
- `status_summary`
- `status_mapping_rules`
- per-target `role`, `review_status_override`, `review_reason`, `target_review_status`, and `profile_gaps`

The evidence regexes were narrowed to path-like and command-like signals so narrative words such as `passed`, `main`, or `validation` no longer count as proof on their own.

`TARGET_TOPIC_ALLOWLIST.json` now carries `target_topic_overrides` for audited needs-update topics, known closed false positives, and the `MERGED_OVERVIEW` topic-local drift gate role.

## Validation

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/checkers/test_check_development_plans_status_matrix_unittest.py
/Users/wangyiliang/.local/bin/python3.11 scripts/checkers/check_development_plans_status_matrix.py --root .
```

Observed:

```text
pytest: 15 passed
matrix: current=partial:0,not_closed:0,no_closure_claim:0
matrix: targets=active_current:0,closed:26,external_blocked:29,retired:6
matrix: reviews=active_current:0,closed:20,external_blocked:29,needs_update:6,retired:6
```
