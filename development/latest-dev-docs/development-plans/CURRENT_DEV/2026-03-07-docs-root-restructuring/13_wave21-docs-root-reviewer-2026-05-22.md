# Wave21 Docs Root Reviewer (2026-05-22)

## Decision
- `unsafe_moves=5` does **not** indicate checker failure; it indicates intentional remaining scoped work.  
- In `CURRENT_DEV`, keep the topic in place and treat it as **`external_blocked`** rather than `closed`/`retired`.
- Justification: checks pass for manifest integrity, but the current content-plan still reserves blocked-broad moves for mixed-index and compatibility-owned roots.

## Evidence
- `python3 scripts/checkers/check_docs_root_content_plan.py`  
  output: `OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=5`.
- `python3 scripts/check_docs_root_migration_manifest.py`  
  output: `OK docs_root_migration_manifest=passed manifests=2 entries=12`.
- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/12_wave20-docs-root-content-move-batch5-evidence-2026-05-22.md`  
  states docs-root migration remains open, architecture-side unsafe moves fell from 6 to 5, and status kept open because integration-level shared indexes are not yet handled in this topic.
- `docs/development/latest-dev-docs-content-plan.json` `remaining_unsafe_moves` (5 entries, ids and reasons):
  1. `development-plans-current-dev-tree`: `CURRENT_DEV` is active status surface and owns shared index files.
  2. `development-plans-main-tree`: `main` remains compatibility-bound pending merged snapshots and shared overview reconciliation.
  3. `development-plans-archive-closed-tree`: mixed roles across development/implementation/architecture/governance.
  4. `frontend-modern-tree`: still has compatibility-root links and shared overview references.
  5. `root-plans-main-tree`: mixed content, file-level classification required before bulk move.
- `check_docs_root_content_plan.py` logic confirms `remaining_unsafe_moves` entries must remain `blocked_broad_move` and carry both blockers: `shared_navigation_sync` and `MERGED_OVERVIEW_drift`.

## Blocking Conditions
- Shared index and merged-overview ownership is still external to this worktree; docs-root content moves are intentionally compatibility-first.
- `CURRENT_DEV` and `main` trees are explicitly designated active/shared surfaces and should not be closed as migrated content yet.
- `frontend-modern` and `root-plans/main` remain semantically mixed and require file-level routing rather than subtree-level move.
- `development-plans/ARCHIVE_CLOSED` still mixes roles; unsafe broad move would break role boundaries.

## 推荐状态
- 建议状态：`external_blocked`.
- 可退回路径：如需继续推进，优先由上游索引/导航主控方解除共享导航与 `MERGED_OVERVIEW` 漂移阻塞后，分批补齐 `remaining_unsafe_moves`。

## 最小验证命令
- `python3 scripts/checkers/check_docs_root_content_plan.py`
- `python3 scripts/check_docs_root_migration_manifest.py`
- `git diff --check`
