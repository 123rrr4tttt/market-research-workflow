# Development Plans Migration Entry

> Date: 2026-05-23
> Status: Wave29 active surface and archive broad-move decomposition; selected main files are target authoritative
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/development/development-plans`
> Shim: `docs/development/development-plans/README.md`

This entry maps low-ambiguity development-planning material from the compatibility root into the future `docs/development/` taxonomy. Wave25 moved the two `development-plans/main` files into this target root and left the old latest-dev-docs paths as compatibility shims.

## Moved Content Batch

| Previous compatibility path | Authoritative target | Role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/development-plans/main/index.md](../../../development/latest-dev-docs/development-plans/main/index.md) | [docs/development/development-plans/main/index.md](./main/index.md) | main entry | content moved; target authoritative |
| [development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md](../../../development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md) | [docs/development/development-plans/main/MERGED_DEVELOPMENT_PLANS.md](./main/MERGED_DEVELOPMENT_PLANS.md) | merged snapshot | content moved; target authoritative |

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/development-plans/main](../../../development/latest-dev-docs/development-plans/main) | [development/latest-dev-docs/development-plans/main/index.md](../../../development/latest-dev-docs/development-plans/main/index.md) | moved-file compatibility shim | target authoritative; source shim retained |
| [development/latest-dev-docs/development-plans/CURRENT_DEV](../../../development/latest-dev-docs/development-plans/CURRENT_DEV) | [development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md) | active plan root shim | content shim; source authoritative; supervisor-owned active surface |

## Compatibility Rule

The moved target files are authoritative for this main development-plans batch. The old latest-dev-docs files remain as compatibility shims until shared navigation fully switches to `docs/development`. `CURRENT_DEV` remains source-authoritative because it is the active status surface; it is not a broad content move candidate and must not be migrated just to reduce the unsafe count.

## Docs Root Closure Evidence

The target development-plans entry carries the post-Wave25 docs-root evidence anchors that the navigation drift checker treats as worker-owned target-root coverage:

- Wave25 development-plans main move: [14_wave25-docs-root-development-main-move-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/14_wave25-docs-root-development-main-move-2026-05-23.md)
- Wave27 root-plans main move: [15_wave27-worker-b-docs-root-root-plans-main-move-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/15_wave27-worker-b-docs-root-root-plans-main-move-2026-05-23.md)
- Wave27 worker A reconciliation: [16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md)
- Wave28 CURRENT_DEV active surface decision: [17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md)
- Wave28 reviewer decision: [17_wave28-docs-root-reviewer-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/17_wave28-docs-root-reviewer-2026-05-23.md)
- Wave28 archive closed classification: [18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md)
- Wave29 archive closed decomposition: [19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md)
- Wave29 shared navigation drift gate: [19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md)
- Wave30 target navigation readback: [20_wave30-docs-root-navigation-target-readback-2026-05-23.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/20_wave30-docs-root-navigation-target-readback-2026-05-23.md)

## Archive Closed Classification

Wave28 classified the remaining `ARCHIVE_CLOSED` broad-move candidate without moving source files. The file-level ledger is [archive-closed-file-classification-2026-05-23.json](./archive-closed-file-classification-2026-05-23.json).

The ledger covers 195 files and 1 empty directory under [development/latest-dev-docs/development-plans/ARCHIVE_CLOSED](../../../development/latest-dev-docs/development-plans/ARCHIVE_CLOSED). The broad move remains blocked because the source archive files have not been converted into compatibility shims, and shared navigation plus `MERGED_OVERVIEW` still need synchronization before any target-authoritative archive move is safe.

Wave29 closes `development-plans-archive-closed-tree` as an unsafe broad-tree move by decomposing it into ledger-backed per-file batch work. This does not make the archive target-authoritative. Archive files remain source-authoritative until a later worker creates target files under `docs/development/development-plans/ARCHIVE_CLOSED`, replaces each source file with a compatibility shim pointing to its target, and records those files as `moved_file_batch` entries.
