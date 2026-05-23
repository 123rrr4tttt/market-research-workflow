<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave29 Worker A Docs Root Archive Closed Decomposition

> Date: 2026-05-23
> Worker: docs-root worker A
> Historical status before Wave31/Wave34: unsafe broad-tree move closed; archive content remained source-authoritative at that time.

## Scope

This worker owned only the docs-root metadata surfaces for `development-plans-archive-closed-tree`:

- [docs/development/development-plans/archive-closed-file-classification-2026-05-23.json](../../../../../docs/development/development-plans/archive-closed-file-classification-2026-05-23.json)
- [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json)
- [docs/development/latest-dev-docs-entry-manifest.json](../../../../../docs/development/latest-dev-docs-entry-manifest.json)
- [docs/development/development-plans/README.md](../../../../../docs/development/development-plans/README.md)

No shared latest-dev-docs top index was edited. No source archive file under [development/latest-dev-docs/development-plans/ARCHIVE_CLOSED](../../ARCHIVE_CLOSED) was rewritten.

## Decision

Wave29 closes the unsafe broad-tree move as the wrong migration primitive. The archive is now represented as `broad_move_decomposed_to_file_batches` in the development content plan and manifest metadata.

At Wave29 this was not yet a content move: the source archive remained authoritative until a later worker performed explicit per-file moved batches. After Wave31/Wave34, this copied topic record itself is now target-authoritative under `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring`; the sentence is retained here as historical context for why Wave29 did not claim closure.

## Evidence

The existing classification ledger still matches the current source tree:

| Check | Result |
|---|---:|
| Source files | 195 |
| Empty source directories | 1 |
| Ledger/source path diff | 0 |

The broad move can be closed because the ledger provides a stable file-level queue. It cannot be marked `moved_file_batch` yet because that requires target files and source compatibility shims for every moved file.

## Mechanical Next Step

Select a small batch from `archive-closed-file-classification-2026-05-23.json`, then for each selected file:

1. Create the target file under `docs/development/development-plans/ARCHIVE_CLOSED/...`.
2. Replace the original source file with a compatibility shim that names and links the target.
3. Add a matching `moved_file_batch` entry to the migration manifest and content plan.
4. Run the docs-root manifest and content-plan checkers.

Shared navigation and `MERGED_OVERVIEW` synchronization should happen in the same integration pass that promotes any archive batch to target-authoritative status.

## Validation

```bash
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_docs_root_migration_manifest.py
```

Observed results:

```text
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=0
OK docs_root_migration_manifest=passed manifests=2 entries=12
```
