# Wave18 Docs Root Content Move Batch 3 Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave18-docs-root-content-move-batch3`
> Branch: `codex/devdocs-wave18-docs-root-content-move-batch3`
> Status: partial; third real moved-file batch landed; shared indexes intentionally unchanged

## Inputs Checked

- Wave18 plan: [wave18-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave18-worktree-plan-2026-05-22.md)
- Wave16 content move evidence: [08_wave16-docs-root-content-move-batch-evidence-2026-05-22.md](./08_wave16-docs-root-content-move-batch-evidence-2026-05-22.md)
- Wave17 content move evidence: [09_wave17-docs-root-content-move-batch2-evidence-2026-05-22.md](./09_wave17-docs-root-content-move-batch2-evidence-2026-05-22.md)
- Architecture migration manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | A third small architecture content batch moved from shim-only planning into target-authoritative docs content. | [docs/architecture/root-plans/A_ARCHITECTURE/README.md](../../../../../docs/architecture/root-plans/A_ARCHITECTURE/README.md) and [docs/architecture/root-plans/A_ARCHITECTURE/project-standardization-development-directions-2026-03-01.md](../../../../../docs/architecture/root-plans/A_ARCHITECTURE/project-standardization-development-directions-2026-03-01.md) now carry the content body. |
| 兼容保留 | The previous latest-dev-docs paths remain readable as compatibility shims. | [development/latest-dev-docs/root-plans/A_ARCHITECTURE/README.md](../../../../../development/latest-dev-docs/root-plans/A_ARCHITECTURE/README.md) and [development/latest-dev-docs/root-plans/A_ARCHITECTURE/project-standardization-development-directions-2026-03-01.md](../../../../../development/latest-dev-docs/root-plans/A_ARCHITECTURE/project-standardization-development-directions-2026-03-01.md) point to the moved targets. |
| 范围收缩 | Architecture remaining unsafe broad moves dropped from 3 to 2, and total content-plan unsafe moves dropped from 8 to 7. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) validates `moved_file_batch` entries and reports `unsafe_moves=7`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Shared indexes and `MERGED_OVERVIEW` are still owned by supervisor integration and were not edited in this worker branch. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `root-plans-architecture-tree` | `development/latest-dev-docs/root-plans/A_ARCHITECTURE/README.md` | `docs/architecture/root-plans/A_ARCHITECTURE/README.md` | `content_moved_batch` / `moved_file_batch` |
| `root-plans-architecture-tree` | `development/latest-dev-docs/root-plans/A_ARCHITECTURE/project-standardization-development-directions-2026-03-01.md` | `docs/architecture/root-plans/A_ARCHITECTURE/project-standardization-development-directions-2026-03-01.md` | `content_moved_batch` / `moved_file_batch` |

## Navigation Boundary

This batch intentionally leaves shared supervisor indexes untouched:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

`docs/architecture/root-plans/README.md` is the local docs-root entry for the moved files. The old latest-dev-docs files remain compatibility shims until supervisor integration updates shared navigation and shared overview references.

## Validation

```bash
python3 scripts/check_current_dev_wave18_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/architecture/root-plans \
  --link-path development/latest-dev-docs/root-plans/A_ARCHITECTURE \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
git diff --check
```
