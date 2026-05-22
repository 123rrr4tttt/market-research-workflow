# Wave16 Docs Root Content Move Batch Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave16-docs-root-content-move-batch`
> Branch: `codex/devdocs-wave16-docs-root-content-move-batch`
> Status: partial; one real moved-file batch landed; shared indexes intentionally unchanged

## Inputs Checked

- Wave16 plan: [wave16-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave16-worktree-plan-2026-05-22.md)
- Wave9 migration manifest evidence: [04_wave9-8-docs-root-migration-manifest-evidence-2026-05-22.md](./04_wave9-8-docs-root-migration-manifest-evidence-2026-05-22.md)
- Wave11 navigation promotion evidence: [06_wave11-docs-root-navigation-promotion-evidence-2026-05-22.md](./06_wave11-docs-root-navigation-promotion-evidence-2026-05-22.md)
- Wave12 content-plan gate evidence: [07_wave12-docs-root-content-plan-gate-evidence-2026-05-22.md](./07_wave12-docs-root-content-plan-gate-evidence-2026-05-22.md)
- Architecture migration manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 已推进 | One backend-core architecture file moved from shim-only planning into target-authoritative docs content. | [docs/architecture/backend-core/A_ARCHITECTURE/README.backend-core.md](../../../../../docs/architecture/backend-core/A_ARCHITECTURE/README.backend-core.md) now carries the content body. |
| 兼容保留 | The previous latest-dev-docs path remains readable as a compatibility shim. | [development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md](../../../../../development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md) points to the moved target. |
| 范围收缩 | Architecture remaining unsafe broad moves dropped from 5 to 4, and total content-plan unsafe moves dropped from 10 to 9. | [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) validates `moved_file_batch` entries and reports `unsafe_moves=9`. |
| 未封口 | Keep docs-root restructuring in `CURRENT_DEV`. | Shared indexes and `MERGED_OVERVIEW` are still owned by supervisor integration and were not edited in this worker branch. |

## Moved Batch

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `backend-core-architecture-tree` | `development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md` | `docs/architecture/backend-core/A_ARCHITECTURE/README.backend-core.md` | `content_moved_batch` / `moved_file_batch` |

## Checker Updates

- [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py) now allows `content_moved_batch` entries and checks moved target files, old compatibility shims, and target README discoverability.
- [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py) now allows `moved_file_batch` entries and requires the content-plan `moved_files` list to match the migration manifest.

## Validation

```bash
python3 scripts/check_current_dev_wave16_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/architecture \
  --link-path docs/development \
  --link-path development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring \
  --link-path development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-后续安排/04_status-evidence-and-minimum-dev-plan-2026-05-22.md
PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 scripts/check_current_dev_status_evidence.py
python3 -m py_compile scripts/check_docs_root_migration_manifest.py scripts/checkers/check_docs_root_content_plan.py
git diff --check
```

## Remaining Boundary

This batch intentionally does not edit:

- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`

Supervisor integration still needs to synchronize shared navigation and overview references before this topic can close.
