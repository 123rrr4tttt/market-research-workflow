# Wave11 Docs Root Navigation Promotion Evidence

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave11-docs-root-navigation`
> Branch: `codex/devdocs-wave11-docs-root-navigation`
> Status: partial; `docs/development` local navigation promoted; shared indexes intentionally unchanged

## Inputs Checked

- Wave11 plan: [wave11-worktree-plan-2026-05-22.md](../../../automation-runs/dev-docs-folder-audit-2026-05-22/wave11-worktree-plan-2026-05-22.md)
- Wave10 content-shim evidence: [05_wave10-8-docs-root-content-shim-evidence-2026-05-22.md](./05_wave10-8-docs-root-content-shim-evidence-2026-05-22.md)
- Development root README: [docs/development/README.md](../../../../../docs/development/README.md)
- Development root manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)

## Result

| State | Judgment | Evidence |
|---|---|---|
| 未封口 | Keep this topic in `CURRENT_DEV`. | This batch promotes reader navigation only; it does not move content and does not update latest-dev-docs shared indexes. |
| 已推进 | `docs/development` now has a bounded local navigation batch. | `docs/development/README.md` exposes `development-plans`, `frontend-modern`, and `root-plans` shim entries with manifest entry IDs and compatibility entries. |
| 可检查 | The promotion is machine-checkable. | `docs/development/latest-dev-docs-entry-manifest.json` declares `navigation_promotions`, and `scripts/check_docs_root_migration_manifest.py` validates the root README, target README paths, manifest entry IDs, and compatibility entries. |

## Promoted Batch

| Target root | Local navigation entry | Manifest entry IDs | Compatibility entry |
|---|---|---|---|
| `docs/development/development-plans` | [docs/development/development-plans/README.md](../../../../../docs/development/development-plans/README.md) | `development-plans-main-index`, `development-plans-main-merged`, `development-plans-current-dev-root` | `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md` |
| `docs/development/frontend-modern` | [docs/development/frontend-modern/README.md](../../../../../docs/development/frontend-modern/README.md) | `frontend-modern-main-index`, `frontend-modern-main-merged` | `development/latest-dev-docs/frontend-modern/main/index.md` |
| `docs/development/root-plans` | [docs/development/root-plans/README.md](../../../../../docs/development/root-plans/README.md) | `root-plans-f-plan-index`, `root-plans-main-index-mixed` | `development/latest-dev-docs/root-plans/F_PLAN/index.md` |

## Checker Contract

The manifest checker now treats `navigation_promotions` as an optional root-level contract:

- promotion status must be `navigation_promoted`;
- `root_readme` must be the manifest root README;
- the declared navigation section must exist in the root README;
- each promoted target must resolve to `target_root/README.md`;
- every listed manifest entry ID must exist and target the same shim README;
- each compatibility entry must remain under `development/latest-dev-docs` and exist;
- the root README must mention the target root, target README, compatibility entry, and manifest entry IDs.

## Partial Boundary

This topic remains partial for four reasons:

1. `development/latest-dev-docs` remains the authoritative content root.
2. The shared indexes remain untouched for supervisor integration:
   - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
   - `development/latest-dev-docs/development-plans/INDEX.md`
   - `development/latest-dev-docs/README.md`
   - `development/latest-dev-docs/MERGED_OVERVIEW.md`
3. `docs/architecture` still has content shims but no Wave11 navigation promotion in this batch.
4. No source content was moved; this only promotes local reader navigation for the existing development-root shims.

## Validation

```bash
python3 scripts/check_current_dev_wave11_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/check_latest_dev_docs_structure.py \
  --link-path docs/development \
  --link-path docs/architecture \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
python3 -m py_compile scripts/check_current_dev_wave11_plan.py scripts/check_docs_root_migration_manifest.py scripts/check_latest_dev_docs_structure.py
git diff --check
```
