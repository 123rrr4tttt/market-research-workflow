# Wave27 Worker A Docs Root Root-Plans Main Reconciliation

> Date: 2026-05-23
> Worker: docs-root worker A
> Status: partial; root-plans main moved-file batch verified in forked workspace; docs-root migration remains open while `unsafe_moves=2`

## Inputs Checked

- Mapping plan: [01_docs-root-restructuring-mapping-2026-03-07.md](./01_docs-root-restructuring-mapping-2026-03-07.md)
- Wave21 retained-partial decision: [13_wave21-docs-root-closure-priority-2026-05-22.md](./13_wave21-docs-root-closure-priority-2026-05-22.md)
- Wave25 development main move: [14_wave25-docs-root-development-main-move-2026-05-23.md](./14_wave25-docs-root-development-main-move-2026-05-23.md)
- Development migration manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Development content plan: [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)

## Authority List

The authoritative remaining unsafe list is `remaining_unsafe_moves` in [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json).

At worker start, the task input expected 4 unsafe moves after Wave25:

- `development-plans-current-dev-tree`
- `development-plans-archive-closed-tree`
- `frontend-modern-tree`
- `root-plans-main-tree`

The workspace already contained a concurrent Wave27 frontend-modern moved-file batch before this root-plans batch was finalized, so the live pre-batch list had 3 unsafe moves:

- `development-plans-current-dev-tree`
- `development-plans-archive-closed-tree`
- `root-plans-main-tree`

This worker reconciled and verified the `root-plans-main-tree` moved-file batch in the forked workspace, leaving 2 unsafe moves:

- `development-plans-current-dev-tree`
- `development-plans-archive-closed-tree`

## Moved Batch

`development/latest-dev-docs/root-plans/main` contains exactly two files. Both are consolidated development planning material rather than implementation, architecture, or governance policy, so the complete directory can be promoted as one file-level moved batch under `docs/development/root-plans/main/`.

| Manifest entry | Previous compatibility path | Authoritative target | Checker mode |
|---|---|---|---|
| `root-plans-main-index-mixed` | `development/latest-dev-docs/root-plans/main/index.md` | `docs/development/root-plans/main/index.md` | `content_moved_batch` / `moved_file_batch` |
| `root-plans-main-index-mixed` | `development/latest-dev-docs/root-plans/main/MERGED_PLAN.md` | `docs/development/root-plans/main/MERGED_PLAN.md` | `content_moved_batch` / `moved_file_batch` |

## Compatibility

- The previous latest-dev-docs files remain readable as compatibility shims.
- [docs/development/root-plans/README.md](../../../../../docs/development/root-plans/README.md) now records the moved content batch and the remaining `F_PLAN` shim boundary.
- [docs/development/README.md](../../../../../docs/development/README.md) now records the live unsafe-move count and root-plans main authority status.
- The manifest/content-plan source boundary for frontend-modern was normalized to the `main/` directory because the existing checker requires moved files to sit under the manifest source path.
- A concurrent consumer-side archive move left stale `CURRENT_DEV` links in shared indexes; worker A mechanically synchronized those links to `ARCHIVE_EXTERNAL_BLOCKED` so the expanded docs/development link check passes.

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
  --link-path development/latest-dev-docs/README.md \
  --link-path development/latest-dev-docs/MERGED_OVERVIEW.md \
  --link-path development/latest-dev-docs/development-plans/INDEX.md \
  --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring
git diff --check -- docs/development development/latest-dev-docs/root-plans/main \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring \
  development/latest-dev-docs/README.md development/latest-dev-docs/MERGED_OVERVIEW.md \
  development/latest-dev-docs/development-plans/INDEX.md
```

Observed results:

```text
OK docs_root_migration_manifest=passed manifests=2 entries=12
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=2
OK latest_dev_docs_structure=passed markdown_link_files=30 markdown_links=1324
```

## Risk

`development-plans/CURRENT_DEV` and `development-plans/ARCHIVE_CLOSED` remain compatibility-bound. Closing the docs-root restructuring topic still requires supervisor-owned status/navigation synchronization and archive file-level classification.
