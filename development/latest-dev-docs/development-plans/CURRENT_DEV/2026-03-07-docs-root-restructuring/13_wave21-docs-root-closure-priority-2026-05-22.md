# Wave21 Docs Root Closure Priority

> Date: 2026-05-22
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave21-docs-root-closer`
> Branch: `codex/devdocs-wave21-docs-root-closer`
> decision: retained_partial

## Inputs Checked

- Content-plan checker: [scripts/checkers/check_docs_root_content_plan.py](../../../../../scripts/checkers/check_docs_root_content_plan.py)
- Migration manifest checker: [scripts/check_docs_root_migration_manifest.py](../../../../../scripts/check_docs_root_migration_manifest.py)
- Development content plan: [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)
- Architecture content plan: [docs/architecture/latest-dev-docs-content-plan.json](../../../../../docs/architecture/latest-dev-docs-content-plan.json)
- Wave16-Wave20 evidence files in this topic directory.

## Decision

`2026-03-07-docs-root-restructuring` cannot be safely closed in Wave21. Keep it as `retained_partial`, not `closed` and not `external_blocked`.

The closure priority changed from adding more evidence to reducing the `CURRENT_DEV` partial count, but this topic still has repo-local migration work that is explicitly unsafe under the current worker scope. The remaining blocker is not an external runtime dependency; it is an internal docs-root integration boundary.

## Current State

| Surface | Current result | Closure implication |
|---|---:|---|
| `docs/architecture/latest-dev-docs-content-plan.json` | 5 entries, 5 `moved_file_batch`, 0 `remaining_unsafe_moves` | Architecture side is locally migratable and no longer blocks by itself. |
| `docs/development/latest-dev-docs-content-plan.json` | 7 entries, 0 `moved_file_batch`, 5 `remaining_unsafe_moves` | Development side remains shim-authoritative and still blocks closure. |
| Combined content-plan gate | `unsafe_moves=5` | Topic cannot be migrated out of `CURRENT_DEV` yet. |

## Last Blocker

The final blocker is the development-side content plan:

- `development-plans-current-dev-tree` still includes shared status/navigation files owned by supervisor integration.
- `development-plans-main-tree` is still compatibility-bound until merged snapshots and shared overview references are reconciled.
- `development-plans-archive-closed-tree` still requires file-level classification before moving mixed archive content.
- `frontend-modern-tree` still depends on shared navigation, `MERGED_OVERVIEW`, and link-check reconciliation.
- `root-plans-main-tree` remains mixed and requires file-level classification before any broad move.

These required gates remain open in the manifest data:

- `shared_navigation_sync`
- `MERGED_OVERVIEW_drift`
- `topic_status_sync`
- `file_level_classification`
- `link_check`

## Migratable Reasons

- Wave16-Wave20 landed real target-authoritative architecture batches.
- The architecture content plan now has no remaining unsafe moves.
- Both docs-root validators pass on the current manifests and moved-file shims.

## Non-Migratable Reasons

- The development content plan still reports 5 unsafe broad moves.
- Closing this topic would require updating shared status/navigation surfaces, including `CURRENT_DEV` status and shared overview references, which are explicitly outside this worker's write scope.
- The topic cannot be converted to `external_blocked` because the blockers are not external services or public runtime dependencies; they are repo-local docs integration and classification gates.
- Archiving from `CURRENT_DEV` now would reduce the partial count only cosmetically while leaving authoritative development content in compatibility shims.

## Validation Commands

```bash
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_docs_root_migration_manifest.py
```

Observed results:

```text
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=5
OK docs_root_migration_manifest=passed manifests=2 entries=12
```

## Next Safe Closure Path

1. Move the remaining development-side content only as small file batches, not broad directory moves.
2. Classify mixed `ARCHIVE_CLOSED` and `root-plans/main` content before moving it under `docs/development`.
3. Reconcile shared navigation, `CURRENT_DEV` status, and `MERGED_OVERVIEW` in a supervisor-owned integration pass.
4. Rerun the two docs-root validators and the relevant latest-dev-docs link checks before archiving this topic.
