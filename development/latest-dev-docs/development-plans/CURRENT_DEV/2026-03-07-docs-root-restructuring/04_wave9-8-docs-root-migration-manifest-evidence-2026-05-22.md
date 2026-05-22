# Wave9-8 Docs Root Migration Manifest Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave9-docs-root-migration`
> Branch: `codex/devdocs-wave9-docs-root-migration`
> Status: partial; first manifest batch added; shared indexes intentionally unchanged

## Inputs Checked

- Original plan: [01_docs-root-restructuring-mapping-2026-03-07.md](./01_docs-root-restructuring-mapping-2026-03-07.md)
- Wave6 closure gap: [02_wave6-docs-root-restructuring-evidence-closure-gap-2026-05-22.md](./02_wave6-docs-root-restructuring-evidence-closure-gap-2026-05-22.md)
- Wave7 target-root evidence: [03_wave7-5-docs-root-targets-evidence-2026-05-22.md](./03_wave7-5-docs-root-targets-evidence-2026-05-22.md)
- Development root manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Architecture root manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 未封口 | Keep this topic in `CURRENT_DEV`. | No historical content was moved and shared navigation remains compatibility-bound. |
| 已推进 | First target-root manifest batch now exists. | `docs/development` and `docs/architecture` each have machine-checkable manifests and per-source entry README files. |
| 需更新 | Future integration must decide whether to promote these mappings into shared indexes. | This worker intentionally did not edit `development/latest-dev-docs/README.md`, `MERGED_OVERVIEW.md`, or development-plan indexes. |

## Mapped Batch

### `docs/development`

- `development/latest-dev-docs/development-plans/main/index.md`
- `development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV`
- `development/latest-dev-docs/frontend-modern/main/index.md`
- `development/latest-dev-docs/frontend-modern/main/MERGED_FRONTEND_MODERN.md`
- `development/latest-dev-docs/root-plans/F_PLAN/index.md`
- `development/latest-dev-docs/root-plans/main/index.md`

### `docs/architecture`

- `development/latest-dev-docs/backend-core/A_ARCHITECTURE`
- `development/latest-dev-docs/backend-docs/A_ARCHITECTURE`
- `development/latest-dev-docs/development-plans/A_ARCHITECTURE`
- `development/latest-dev-docs/ops-frontend/A_ARCHITECTURE`
- `development/latest-dev-docs/root-plans/A_ARCHITECTURE`

## Authority Boundary

The new manifests are authoritative for migration mapping only. The mapped source paths remain authoritative for content until a later batch performs a content move or compatibility shim and updates shared navigation in one integration pass.

## Validation

```bash
python3 scripts/check_docs_root_migration_manifest.py

python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path docs/architecture \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring

python3 -m py_compile scripts/check_docs_root_migration_manifest.py
git diff --check
```

## Remaining Closure Gap

This topic is still partial because the readable compatibility entry remains `development/latest-dev-docs`. Closure requires an integration batch that promotes selected manifest mappings into shared navigation, moves or shims a real content batch, and reruns the same structure/link checks against the changed paths.
