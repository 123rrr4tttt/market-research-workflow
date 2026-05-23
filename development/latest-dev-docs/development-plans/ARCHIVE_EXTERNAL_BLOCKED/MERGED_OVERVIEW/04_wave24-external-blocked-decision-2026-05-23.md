# Wave24 MERGED_OVERVIEW External Blocked Decision

- Date: 2026-05-23
- Status: `external_blocked`
- Previous CURRENT_DEV status: `partial`
- Decision: migrate the topic-local `CURRENT_DEV/MERGED_OVERVIEW` drift folder into `ARCHIVE_EXTERNAL_BLOCKED`

## Decision

This folder is not the top-level `development/latest-dev-docs/MERGED_OVERVIEW.md` navigation surface. It is a topic-local historical RAG drift gate. Wave13 proved that its retired RAG anchors are stale and that the current authority is the local-index/vectorization evidence path.

The folder should no longer count as an active `CURRENT_DEV` partial. It remains `external_blocked`, not `retired`, because the unresolved conditions are live/vector optional dependency readiness, production semantic quality, and global vector contract closure owned by the active vectorization topics.

## Repo-Local Evidence

- `scripts/check_current_dev_merged_overview_drift_gate.py`
- `03_wave13-current-merged-overview-rag-drift-gate-2026-05-22.md`
- `main/backend/app/services/local_index/schema.py`
- `main/backend/app/services/local_index/service.py`
- `main/backend/app/services/local_index/adapters/lancedb_adapter.py`
- `ops/search-lab/scripts/wave10_vectorization_quality_gate.py`
- `ops/search-lab/scripts/wave12_provider_readiness_gate.py`

## External Blockers

- Live optional dependency readiness for the current vector stack.
- Production semantic relevance / embedding quality proof.
- Global vector object and main-search evidence-hit contract closure in the active vectorization topics.

## Verification

```bash
/Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_merged_overview_drift_gate.py
/Users/wangyiliang/.local/bin/python3.11 scripts/check_latest_dev_docs_structure.py --link-path development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/MERGED_OVERVIEW
```
