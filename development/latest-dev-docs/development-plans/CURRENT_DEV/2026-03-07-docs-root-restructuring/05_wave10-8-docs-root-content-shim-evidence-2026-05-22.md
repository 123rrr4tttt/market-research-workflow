# Wave10-8 Docs Root Content Shim Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave10-docs-root-content-shim`
> Branch: `codex/devdocs-wave10-docs-root-content-shim`
> Status: partial; first content shim batch added; shared indexes intentionally unchanged

## Inputs Checked

- Wave10 plan: [wave10-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave10-worktree-plan-2026-05-22.md)
- Wave9 manifest evidence: [04_wave9-8-docs-root-migration-manifest-evidence-2026-05-22.md](./04_wave9-8-docs-root-migration-manifest-evidence-2026-05-22.md)
- Development root manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Architecture root manifest: [docs/architecture/latest-dev-docs-entry-manifest.json](../../../../../docs/architecture/latest-dev-docs-entry-manifest.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 未封口 | Keep this topic in `CURRENT_DEV`. | No historical content was moved and shared navigation remains compatibility-bound. |
| 已推进 | The Wave9 manifest batch now has an explicit content shim layer. | Every manifest entry declares `source`, `target_root`, `shim`, and `compatibility_entry`; target README files expose the same paths for readers. |
| 仍需集成 | Integration still owns shared navigation promotion. | This worker did not edit `development/latest-dev-docs/README.md`, `MERGED_OVERVIEW.md`, or development-plan shared indexes. |

## Content Shim Batch

### `docs/development`

| Target root | Shim README | Compatibility entries |
|---|---|---|
| `docs/development/development-plans` | [README.md](../../../../../docs/development/development-plans/README.md) | `development-plans/main/index.md`, `development-plans/main/MERGED_DEVELOPMENT_PLANS.md`, `development-plans/CURRENT_DEV/INDEX.md` |
| `docs/development/frontend-modern` | [README.md](../../../../../docs/development/frontend-modern/README.md) | `frontend-modern/main/index.md`, `frontend-modern/main/MERGED_FRONTEND_MODERN.md` |
| `docs/development/root-plans` | [README.md](../../../../../docs/development/root-plans/README.md) | `root-plans/F_PLAN/index.md`, `root-plans/main/index.md` |

### `docs/architecture`

| Target root | Shim README | Compatibility entries |
|---|---|---|
| `docs/architecture/backend-core` | [README.md](../../../../../docs/architecture/backend-core/README.md) | `backend-core/A_ARCHITECTURE/README.backend-core.md` |
| `docs/architecture/backend-docs` | [README.md](../../../../../docs/architecture/backend-docs/README.md) | `backend-docs/A_ARCHITECTURE` |
| `docs/architecture/development-plans` | [README.md](../../../../../docs/architecture/development-plans/README.md) | `development-plans/A_ARCHITECTURE/INDEX.md` |
| `docs/architecture/ops-frontend` | [README.md](../../../../../docs/architecture/ops-frontend/README.md) | `ops-frontend/A_ARCHITECTURE/DIR_MAP.md` |
| `docs/architecture/root-plans` | [README.md](../../../../../docs/architecture/root-plans/README.md) | `root-plans/A_ARCHITECTURE/README.md` |

## Checker Contract

`scripts/check_docs_root_migration_manifest.py` now preserves the old `mapped_not_moved` status while enforcing additional rules for `content_shim` entries:

- `source` exists under `development/latest-dev-docs`;
- `target_root` exists under the manifest root;
- `target` and `shim` resolve to `target_root/README.md`;
- `compatibility_entry` exists and is equal to, or inside, the declared source path;
- the target README mentions the source path, target root, shim path, compatibility entry, and the phrase `content shim`.

## Authority Boundary

The compatibility entries remain the content authority. The `docs/development` and `docs/architecture` README files are reader shims only; they do not replace the old root or make duplicate authoritative copies.

## Validation

```bash
python3 scripts/check_current_dev_wave10_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path docs/architecture \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
python3 -m py_compile scripts/check_current_dev_wave10_plan.py scripts/check_docs_root_migration_manifest.py scripts/check_latest_dev_docs_structure.py
git diff --check
```
