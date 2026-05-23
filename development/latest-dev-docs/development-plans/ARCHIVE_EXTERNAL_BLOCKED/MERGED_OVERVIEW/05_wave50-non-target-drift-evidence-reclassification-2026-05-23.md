# Wave50 MERGED_OVERVIEW Drift Evidence Reclassification

- Date: 2026-05-23
- Status: `non_target_topic_local_drift_evidence`
- Previous review status: `external_blocked`
- Decision: remove this folder from the external-blocked target set

## Decision

This folder is a topic-local drift/evidence record, not a real development target.

Wave13 proved that the retired RAG anchors were stale and mapped them to the current local-index/vectorization evidence path. Wave24 moved the folder out of `CURRENT_DEV` so it would not count as `partial`. After the target-topic allowlist split, keeping this folder as an `external_blocked` target double-counts vector production-quality conditions already owned by `2026-05-14-global-vectorization-general-foundation`.

This reclassification does not claim that vector optional dependencies, production semantic quality, or global vector quality are solved. It only changes this folder's role to process evidence.

## Current Routing

- Target owner for vector production quality: [Global Vectorization General Foundation](../2026-05-14-global-vectorization-general-foundation/INDEX.md)
- Drift checker retained for evidence integrity: [scripts/check_current_dev_merged_overview_drift_gate.py](../../../../../scripts/check_current_dev_merged_overview_drift_gate.py)

## Verification

```bash
/Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_merged_overview_drift_gate.py
/Users/wangyiliang/.local/bin/python3.11 scripts/checkers/check_development_plans_status_matrix.py --root . --fail-on-needs-update
/Users/wangyiliang/.local/bin/python3.11 scripts/checkers/check_external_blocker_manifest.py --root .
```
