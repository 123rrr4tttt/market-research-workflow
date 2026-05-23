<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave28 Docs Root Archive Closed Classification

> Date: 2026-05-23
> Worker: docs-root worker A
> Status: partial; `development-plans-archive-closed-tree` is file-level classified but not safe to broad-move

## Scope

This worker handled only the remaining docs-root unsafe move:

- `development-plans-archive-closed-tree`
- Source: [development/latest-dev-docs/development-plans/ARCHIVE_CLOSED](../../ARCHIVE_CLOSED)
- Target root: [docs/development/development-plans](../../../../../docs/development/development-plans)

No source archive file under `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED` was rewritten. A real `moved_file_batch` would require each source file to become a compatibility shim, and this worker's write scope did not allow editing the source archive tree.

## Result

Wave28 added a file-level classification snapshot:

- [docs/development/development-plans/archive-closed-file-classification-2026-05-23.json](../../../../../docs/development/development-plans/archive-closed-file-classification-2026-05-23.json)

The ledger covers the current source snapshot:

| Item | Count |
|---|---:|
| Classified files | 195 |
| Empty directories | 1 |

Classification counts:

| Classification | Count |
|---|---:|
| `architecture_or_runtime_design_record` | 32 |
| `archive_navigation` | 12 |
| `development_archive_record` | 31 |
| `development_planning_record` | 52 |
| `governance_or_control_plane_record` | 8 |
| `implementation_or_validation_record` | 60 |

The content plan now records that `file_level_classification` is no longer the blocker for this unsafe move. The remaining gates are:

- `source_compatibility_shim_conversion`
- `shared_navigation_sync`
- `MERGED_OVERVIEW_drift`

## Why It Remains Unsafe

The checker only treats an entry as a real `moved_file_batch` when:

- the target file exists under `docs/development`;
- the original `development/latest-dev-docs/...` file still exists as a compatibility shim;
- the source shim explicitly points to the target.

Those source-shim writes are outside this worker's allowed write scope. Marking the archive as moved without converting sources into compatibility shims would create false authority and break the docs-root checker contract.

## Validation

```bash
python3 -m json.tool docs/development/latest-dev-docs-content-plan.json >/dev/null
python3 -m json.tool docs/development/latest-dev-docs-entry-manifest.json >/dev/null
python3 -m json.tool docs/development/development-plans/archive-closed-file-classification-2026-05-23.json >/dev/null
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
comm -3 <(find development/latest-dev-docs/development-plans/ARCHIVE_CLOSED -type f | sort) <(jq -r '.entries[].source' docs/development/development-plans/archive-closed-file-classification-2026-05-23.json | sort)
```

Observed results:

```text
OK docs_root_migration_manifest=passed manifests=2 entries=12
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=1
classification ledger diff: empty
```

## Risk

The source archive tree changed during Wave28 due a concurrent frontend i18n archive closure. This worker regenerated the classification ledger against the current source snapshot and did not edit the source archive. A later owner can safely convert this classified archive into target-authoritative moved-file batches only after source compatibility shims and shared navigation are updated together.
