<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave28 Docs Root Current-Dev Active Surface Decision

> Date: 2026-05-23
> Worker: docs-root worker B
> Status: partial; `development-plans-current-dev-tree` is now supervisor-owned active surface, not a remaining unsafe broad move

## Inputs Checked

- Development migration manifest: [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- Development content plan: [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)
- Development target README: [docs/development/README.md](../../../../../docs/development/README.md)
- Development plans target README: [docs/development/development-plans/README.md](../../../../../docs/development/development-plans/README.md)
- Previous Wave27 evidence: [16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md](./16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md)

## Decision

`development/latest-dev-docs/development-plans/CURRENT_DEV` must not be migrated as a broad docs-root content move.

The tree is a live supervisor-owned status surface:

- [development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md](../INDEX.md) is the active navigation board for unfinished topics.
- [development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md](../STATUS_AUDIT_2026-04-07.md) owns the current closure status accounting.
- Topic directories are still being archived, retired, or blocked one by one during closure waves.

Therefore the safe state is not "move this tree later"; the safe state is "keep this tree source-authoritative until the supervisor closure process has no live status role left." Wave28 records that rule explicitly as `supervisor_owned_active_surface` in the content plan.

## Manifest And Content Plan Changes

- `development-plans-current-dev-tree` moved from `remaining_unsafe_moves` to `supervisor_owned_active_surfaces`.
- `development-plans-current-dev-root` remains `content_shim` and `source_authoritative`.
- `move_allowed` remains `false`.
- `CURRENT_DEV` remains readable through [development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md](../INDEX.md).

This reduces the docs-root unsafe broad-move count without pretending the active status tree has been migrated.

## Why This Is Not A Partial-Reduction Shortcut

Moving `CURRENT_DEV` just to reduce a metric would be unsafe because it would duplicate or relocate live closure state while other closure waves are still editing the same status surface. The reduction is valid only because Wave28 changes the classification: `CURRENT_DEV` is no longer treated as a pending content migration candidate.

The docs-root restructuring topic remains `partial`. The remaining unsafe broad move is:

| Unsafe move | Reason to keep open |
|---|---|
| `development-plans-archive-closed-tree` | Closed archives mix development, implementation, architecture, and governance roles; file-level classification is still required. |

## Validation

```bash
python3 -m json.tool docs/development/latest-dev-docs-content-plan.json >/dev/null
python3 -m json.tool docs/development/latest-dev-docs-entry-manifest.json >/dev/null
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
```

Observed results:

```text
OK docs_root_migration_manifest=passed manifests=2 entries=12
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=1
```

## Risk

Shared latest-dev-docs navigation still points at the active compatibility root, by design. A later supervisor integration pass must keep `CURRENT_DEV` under `development/latest-dev-docs` until topic-level closure removes the active status surface role.
