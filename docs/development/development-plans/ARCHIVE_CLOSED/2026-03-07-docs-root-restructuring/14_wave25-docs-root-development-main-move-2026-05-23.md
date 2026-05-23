<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/14_wave25-docs-root-development-main-move-2026-05-23.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/14_wave25-docs-root-development-main-move-2026-05-23.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave25 Docs Root Development Main Move Evidence

> Date: 2026-05-23
> Status: partial; sixth real moved-file batch landed; docs-root migration remains open while `unsafe_moves=4`

## Inputs Checked

- Wave21 retained-partial decision: [13_wave21-docs-root-closure-priority-2026-05-22.md](./13_wave21-docs-root-closure-priority-2026-05-22.md)
- Wave21 reviewer: [13_wave21-docs-root-reviewer-2026-05-22.md](./13_wave21-docs-root-reviewer-2026-05-22.md)
- Development migration manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Development content plan: [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | The low-risk `development-plans/main` files moved from shim-only planning into target-authoritative docs content. | [docs/development/development-plans/main/index.md](../../../../../docs/development/development-plans/main/index.md) and [docs/development/development-plans/main/MERGED_DEVELOPMENT_PLANS.md](../../../../../docs/development/development-plans/main/MERGED_DEVELOPMENT_PLANS.md) are now authoritative targets. |
| 兼容保留 | The previous latest-dev-docs paths remain readable as compatibility shims. | [development/latest-dev-docs/development-plans/main/index.md](./../../main/index.md) and [development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md](./../../main/MERGED_DEVELOPMENT_PLANS.md) point to the moved targets. |
| 范围收缩 | Development-side unsafe moves dropped by one; total docs-root content-plan unsafe moves dropped from 5 to 4. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) reports `unsafe_moves=4`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Remaining blockers are still repo-local: active `CURRENT_DEV` status surface, mixed closed archive classification, frontend-modern shared navigation, and mixed root-plans main classification. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `development-plans-main-index` | `development/latest-dev-docs/development-plans/main/index.md` | `docs/development/development-plans/main/index.md` | `content_moved_batch` / `moved_file_batch` |
| `development-plans-main-merged` | `development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md` | `docs/development/development-plans/main/MERGED_DEVELOPMENT_PLANS.md` | `content_moved_batch` / `moved_file_batch` |

## Remaining Unsafe Moves

| Unsafe move | Reason to keep open |
|---|---|
| `development-plans-current-dev-tree` | `CURRENT_DEV` is the active status surface and still requires topic-status synchronization. |
| `development-plans-archive-closed-tree` | Closed archives mix development, implementation, architecture, and governance roles; file-level classification is still required. |
| `frontend-modern-tree` | The tree still has compatibility-root links and shared overview references. |
| `root-plans-main-tree` | Mixed main content still requires file-level classification before any move. |

## Validation

```bash
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
git diff --check
```
