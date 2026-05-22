# Wave17 Docs Root Content Move Batch 2 Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave17-docs-root-content-move-batch2`
> Branch: `codex/devdocs-wave17-docs-root-content-move-batch2`
> Status: partial; second real moved-file batch landed; shared indexes intentionally unchanged

## Inputs Checked

- Wave17 plan: [wave17-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave17-worktree-plan-2026-05-22.md)
- Wave16 content move evidence: [08_wave16-docs-root-content-move-batch-evidence-2026-05-22.md](./08_wave16-docs-root-content-move-batch-evidence-2026-05-22.md)
- Architecture migration manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | A second small architecture content batch moved from shim-only planning into target-authoritative docs content. | [docs/architecture/ops-frontend/A_ARCHITECTURE/DIR_MAP.md](../../../../../docs/architecture/ops-frontend/A_ARCHITECTURE/DIR_MAP.md) and [docs/architecture/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md](../../../../../docs/architecture/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md) now carry the content body. |
| 兼容保留 | The previous latest-dev-docs paths remain readable as compatibility shims. | [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md](../../../../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md) and [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md](../../../../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md) point to the moved targets. |
| 范围收缩 | Architecture remaining unsafe broad moves dropped from 4 to 3, and total content-plan unsafe moves dropped from 9 to 8. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) validates `moved_file_batch` entries and reports `unsafe_moves=8`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Shared indexes and `MERGED_OVERVIEW` are still owned by supervisor integration and were not edited in this worker branch. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `ops-frontend-architecture-tree` | `development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md` | `docs/architecture/ops-frontend/A_ARCHITECTURE/DIR_MAP.md` | `content_moved_batch` / `moved_file_batch` |
| `ops-frontend-architecture-tree` | `development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md` | `docs/architecture/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md` | `content_moved_batch` / `moved_file_batch` |

## Navigation Boundary

This batch intentionally leaves shared supervisor indexes untouched:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

`docs/architecture/ops-frontend/README.md` is the local docs-root entry for the moved files. The old latest-dev-docs files remain compatibility shims until supervisor integration updates shared navigation and shared overview references.

## Validation

```bash
python3 scripts/check_current_dev_wave17_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/architecture/ops-frontend \
  --link-path development/latest-dev-docs/ops-frontend/A_ARCHITECTURE \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
git diff --check
```
