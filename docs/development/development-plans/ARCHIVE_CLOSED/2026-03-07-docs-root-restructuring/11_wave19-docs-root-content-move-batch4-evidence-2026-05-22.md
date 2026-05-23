<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/11_wave19-docs-root-content-move-batch4-evidence-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/11_wave19-docs-root-content-move-batch4-evidence-2026-05-22.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave19 Docs Root Content Move Batch 4 Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave19-docs-root-content-move-batch4`
> Branch: `codex/devdocs-wave19-docs-root-content-move-batch4`
> Status: partial; fourth real moved-file batch landed; shared indexes intentionally unchanged

## Inputs Checked

- Wave19 plan: [wave19-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave19-worktree-plan-2026-05-22.md)
- Wave18 content move evidence: [10_wave18-docs-root-content-move-batch3-evidence-2026-05-22.md](./10_wave18-docs-root-content-move-batch3-evidence-2026-05-22.md)
- Architecture migration manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | A fourth architecture content batch moved from shim-only planning into target-authoritative docs content. | [docs/architecture/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md](../../../../../docs/architecture/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md), [docs/architecture/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md](../../../../../docs/architecture/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md), [docs/architecture/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md](../../../../../docs/architecture/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md) now carry the content body, with the rest listed in the moved batch table below. |
| 兼容保留 | The previous latest-dev-docs paths remain readable as compatibility shims. | [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md](../../../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md), [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md](../../../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md), [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md](../../../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md) point to the moved targets, with the rest kept as shims. |
| 范围收缩 | Architecture remaining unsafe broad moves dropped from 2 to 1, and total content-plan unsafe moves dropped from 7 to 6. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) validates `moved_file_batch` entries and reports `unsafe_moves=6`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Shared indexes and `MERGED_OVERVIEW` are still owned by supervisor integration and were not edited in this worker branch. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/PHASE5_LLM_SYMBOLIZATION_MVP.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/PHASE5_LLM_SYMBOLIZATION_MVP.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_DEFINITION.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_DEFINITION.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/STRUCTURED_VS_GRAPH_ALIGNMENT.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/STRUCTURED_VS_GRAPH_ALIGNMENT.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/UNIFIED_COLLECT_ARCHITECTURE.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/UNIFIED_COLLECT_ARCHITECTURE.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/政策数据结构说明.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/政策数据结构说明.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/数据库说明文档.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/数据库说明文档.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/文档去重逻辑说明.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/文档去重逻辑说明.md` | `content_moved_batch` / `moved_file_batch` |
| `backend-docs-architecture-tree` | `development/latest-dev-docs/backend-docs/A_ARCHITECTURE/社交平台图谱生成标准文档.md` | `docs/architecture/backend-docs/A_ARCHITECTURE/社交平台图谱生成标准文档.md` | `content_moved_batch` / `moved_file_batch` |

## Navigation Boundary

This batch intentionally leaves shared supervisor indexes untouched:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

`docs/architecture/backend-docs/README.md` is the local docs-root entry for the moved files. The old latest-dev-docs files remain compatibility shims until supervisor integration updates shared navigation and shared overview references.

## Validation

```bash
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/architecture/backend-docs \
  --link-path development/latest-dev-docs/backend-docs/A_ARCHITECTURE \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
python3 scripts/check_current_dev_wave19_plan.py
git diff --check
```
