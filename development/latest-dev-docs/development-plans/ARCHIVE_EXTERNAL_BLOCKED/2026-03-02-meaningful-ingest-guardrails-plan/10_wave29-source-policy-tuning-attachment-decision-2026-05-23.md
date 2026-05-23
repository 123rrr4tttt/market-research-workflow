# Wave29 Source-Policy Tuning Attachment Decision

Date: 2026-05-23
Scope: `2026-03-02-meaningful-ingest-guardrails-plan`

Decision marker:
`wave29_source_policy_tuning_attachment_reclassified_external`

## Decision

The source-policy tuning attachment should not remain a repo-local blocker inside
this topic.

No successor topic is created in this worker. The current repo-local
source-layer policy shape is already owned by the crawler source expansion
policy matrix, and the meaningful-ingest write path continues to own downstream
URL/content admission.

Decision tags:

- `owned_by_crawler_source_policy_matrix`
- `no_successor_topic_created`
- `source_policy_attachment_resolved_repo_local`
- `live_canary_feedback_required`
- `external_blocked_candidate`
- `do_not_edit_shared_indexes`

## Evidence

The source-layer policy owner is
`docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-crawler-source-expansion/2026-05-22-wave7-crawler-policy-matrix.md`.
That matrix binds `source_policy_action` to `allow`, `downgrade`, and `block`,
and anchors the implementation to:

- `main/backend/app/services/source_library/source_candidate_trust.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/ingest/meaningful_gate.py`
- `main/backend/app/services/discovery/store.py`
- `main/backend/scripts/check_crawler_policy_matrix.py`

The meaningful-ingest topic still owns the write-path guardrails:

- `main/backend/app/services/ingest/meaningful_gate.py`
- `main/backend/app/services/ingest/postprocess_frontdoor.py`
- `main/backend/app/services/ingest/guardrail_rollout.py`
- Wave17 deterministic canary metrics readback evidence
- Wave19 deterministic 24h metrics artifact evidence

## Boundary

The remaining source-policy work is not an unimplemented repository attachment.
It is conditional tuning after live canary feedback exists:

- live guardrail rollout canary against configured services
- production 24h rejection-rate readback
- production 24h inserted-valid ratio readback
- production guardrail rollout counts readback
- operations-owned strict-gate promotion decision
- live-canary-driven source policy tuning, if the feedback shows false positives
  or false negatives

Those conditions are external/live-operational. They should block full closure,
but they should not keep this directory classified as an active repo-local
partial after the topic-local decision is recorded.

## Archive Recommendation

Recommended location: `ARCHIVE_EXTERNAL_BLOCKED`.

This worker does not move the directory and does not update shared navigation
indexes. A later supervisor/index lane should perform the archive move and sync
`CURRENT_DEV/INDEX.md`, `development-plans/INDEX.md`,
`development/latest-dev-docs/README.md`, and
`development/latest-dev-docs/MERGED_OVERVIEW.md`.

## Validation

```bash
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 main/backend/scripts/check_meaningful_ingest_source_policy_attachment.py
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_meaningful_ingest_source_policy_attachment_unittest.py
```

Result: passed.
