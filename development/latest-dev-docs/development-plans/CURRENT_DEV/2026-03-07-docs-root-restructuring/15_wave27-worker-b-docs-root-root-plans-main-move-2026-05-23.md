# Wave27 Worker B Docs Root Root-Plans Main Move Evidence

> Date: 2026-05-23
> Status: partial; worker B moved the root-plans main file batch; docs-root migration remains open while `unsafe_moves=2`

## Inputs Checked

- Latest prior wave: [14_wave25-docs-root-development-main-move-2026-05-23.md](./14_wave25-docs-root-development-main-move-2026-05-23.md)
- Retained-partial decision: [13_wave21-docs-root-closure-priority-2026-05-22.md](./13_wave21-docs-root-closure-priority-2026-05-22.md)
- Development migration manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Development content plan: [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)

## Worker B Scope

| Boundary | Decision |
|---|---|
| Selected batch | `root-plans/main` two-file content move. |
| Worker-A conflict handling | Avoided `CURRENT_DEV` and `ARCHIVE_CLOSED`; preserved the concurrent frontend-modern batch and only normalized its manifest source path so the shared checker could pass. A later Worker A reconciliation note also documents the root-plans state; this worker left it in place and did not revert it. |
| Source boundary | Did not edit `source-library` or frontend source files. |

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | `root-plans/main` moved from shim-only planning into target-authoritative docs content. | [docs/development/root-plans/main/index.md](../../../../../docs/development/root-plans/main/index.md) and [docs/development/root-plans/main/MERGED_PLAN.md](../../../../../docs/development/root-plans/main/MERGED_PLAN.md) are authoritative targets. |
| 兼容保留 | The previous latest-dev-docs paths remain readable as compatibility shims. | [development/latest-dev-docs/root-plans/main/index.md](../../../root-plans/main/index.md) and [development/latest-dev-docs/root-plans/main/MERGED_PLAN.md](../../../root-plans/main/MERGED_PLAN.md) point to the moved targets. |
| 范围收缩 | Development-side unsafe moves dropped by one in worker B; with the concurrent frontend-modern batch, total docs-root content-plan unsafe moves now reports `unsafe_moves=2`. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) reports `unsafe_moves=2`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Remaining blockers are still repo-local: active `CURRENT_DEV` status surface and mixed closed archive classification. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `root-plans-main-index-mixed` | `development/latest-dev-docs/root-plans/main/index.md` | `docs/development/root-plans/main/index.md` | `content_moved_batch` / `moved_file_batch` |
| `root-plans-main-index-mixed` | `development/latest-dev-docs/root-plans/main/MERGED_PLAN.md` | `docs/development/root-plans/main/MERGED_PLAN.md` | `content_moved_batch` / `moved_file_batch` |

## Remaining Unsafe Moves

| Unsafe move | Reason to keep open |
|---|---|
| `development-plans-current-dev-tree` | `CURRENT_DEV` is the active status surface and still requires topic-status synchronization. |
| `development-plans-archive-closed-tree` | Closed archives mix development, implementation, architecture, and governance roles; file-level classification is still required. |

## Validation

```bash
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
git diff --check
```
