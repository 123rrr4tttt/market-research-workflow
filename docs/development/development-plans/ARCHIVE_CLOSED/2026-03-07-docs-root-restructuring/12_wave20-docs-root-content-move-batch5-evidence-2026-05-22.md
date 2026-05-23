<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/12_wave20-docs-root-content-move-batch5-evidence-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/12_wave20-docs-root-content-move-batch5-evidence-2026-05-22.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave20 Docs Root Content Move Batch 5 Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave20-docs-root-content-move-batch5`
> Branch: `codex/devdocs-wave20-docs-root-content-move-batch5`
> Status: partial; fifth real moved-file batch landed; docs-root migration remains open while `unsafe_moves=5`

## Inputs Checked

- Wave20 plan: [wave20-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave20-worktree-plan-2026-05-22.md)
- Wave19 content move evidence: [11_wave19-docs-root-content-move-batch4-evidence-2026-05-22.md](./11_wave19-docs-root-content-move-batch4-evidence-2026-05-22.md)
- Architecture migration manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | The remaining architecture-side unsafe move, `development-plans-architecture-tree`, moved from shim-only planning into target-authoritative docs content. | [docs/architecture/development-plans/A_ARCHITECTURE/INDEX.md](../../../../../docs/architecture/development-plans/A_ARCHITECTURE/INDEX.md) now anchors the moved batch, with all moved files listed below. |
| 兼容保留 | The previous latest-dev-docs paths remain readable as compatibility shims. | [development/latest-dev-docs/development-plans/A_ARCHITECTURE/INDEX.md](../../../../../development/latest-dev-docs/development-plans/A_ARCHITECTURE/INDEX.md) and sibling files point to the moved targets. |
| 范围收缩 | Architecture remaining unsafe moves dropped from 1 to 0; total docs-root content-plan unsafe moves dropped from 6 to 5. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) now permits a per-root zero unsafe list while still reporting total `unsafe_moves=5`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Shared indexes and `MERGED_OVERVIEW` are still owned by supervisor integration and were not edited in this worker branch. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `development-plans-architecture-tree` | `development/latest-dev-docs/development-plans/A_ARCHITECTURE/05_plans_project-standardization-development-directions-2026-03-01.md` | `docs/architecture/development-plans/A_ARCHITECTURE/05_plans_project-standardization-development-directions-2026-03-01.md` | `content_moved_batch` / `moved_file_batch` |
| `development-plans-architecture-tree` | `development/latest-dev-docs/development-plans/A_ARCHITECTURE/06_main_backend_docs_RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | `docs/architecture/development-plans/A_ARCHITECTURE/06_main_backend_docs_RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | `content_moved_batch` / `moved_file_batch` |
| `development-plans-architecture-tree` | `development/latest-dev-docs/development-plans/A_ARCHITECTURE/07_main_backend_docs_UNIFIED_SEARCH_ENHANCEMENT_PLAN.md` | `docs/architecture/development-plans/A_ARCHITECTURE/07_main_backend_docs_UNIFIED_SEARCH_ENHANCEMENT_PLAN.md` | `content_moved_batch` / `moved_file_batch` |
| `development-plans-architecture-tree` | `development/latest-dev-docs/development-plans/A_ARCHITECTURE/08_main_backend_docs_DOC_MERGE_PLAN.md` | `docs/architecture/development-plans/A_ARCHITECTURE/08_main_backend_docs_DOC_MERGE_PLAN.md` | `content_moved_batch` / `moved_file_batch` |
| `development-plans-architecture-tree` | `development/latest-dev-docs/development-plans/A_ARCHITECTURE/11_main_backend_docs_NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md` | `docs/architecture/development-plans/A_ARCHITECTURE/11_main_backend_docs_NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md` | `content_moved_batch` / `moved_file_batch` |
| `development-plans-architecture-tree` | `development/latest-dev-docs/development-plans/A_ARCHITECTURE/INDEX.md` | `docs/architecture/development-plans/A_ARCHITECTURE/INDEX.md` | `content_moved_batch` / `moved_file_batch` |

## Navigation Boundary

This batch intentionally leaves shared supervisor indexes untouched:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

`docs/architecture/development-plans/README.md` is the local docs-root entry for the moved files. The old latest-dev-docs files remain compatibility shims until supervisor integration updates shared navigation, CURRENT_DEV status surfaces, and shared overview references.

## Validation

```bash
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/architecture \
  --link-path development/latest-dev-docs/development-plans/A_ARCHITECTURE \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
python3 scripts/check_current_dev_wave20_plan.py
git diff --check
```
