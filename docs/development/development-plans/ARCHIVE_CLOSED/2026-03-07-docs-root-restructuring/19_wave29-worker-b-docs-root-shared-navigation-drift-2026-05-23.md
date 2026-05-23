<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after docs-root topic archive migration.
> Previous source: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md`
> Migration batch: `docs-root-topic-archive-closed-2026-05-23`

# Wave29 Docs Root Shared Navigation Drift Audit

> Date: 2026-05-23
> Worker: docs-root worker B
> Historical status before Wave31/Wave34: partial; shared navigation and MERGED_OVERVIEW drift remained integration blockers at that time.

## Scope

This worker did not edit global shared indexes:

- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
- `development/latest-dev-docs/development-plans/INDEX.md`
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`

The worker scope is limited to this topic-local note and the read-only checker:

- `scripts/checkers/check_docs_root_navigation_drift.py`

## Current State

Wave29 worker A decomposed the last unsafe broad-tree move, so the content-plan checker now reports `unsafe_moves=0`. The archive is still not target-authoritative content; the current blocker is a ledger-backed per-file batch queue:

- `development-plans-archive-closed-tree`
- source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED`
- target root: `docs/development/development-plans`
- mode: `broad_move_decomposed_to_file_batches`
- remaining gates: `source_compatibility_shim_conversion`, `shared_navigation_sync`, `MERGED_OVERVIEW_drift`

The classified archive ledger exists at:

- `docs/development/development-plans/archive-closed-file-classification-2026-05-23.json`

At Wave29 the source archive files were still source-authoritative records, not compatibility shims. After Wave31/Wave34, this copied topic record itself is now target-authoritative under `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring`; the old blocker description is retained here as historical context for the later navigation-sync closure.

## Machine-Checkable Drift

The new checker audits these contracts:

1. Any remaining docs-root unsafe move and its classification ledger must keep `shared_navigation_sync` and `MERGED_OVERVIEW_drift` as explicit blockers.
2. The decomposed archive queue and its classification ledger must keep `shared_navigation_sync` and `MERGED_OVERVIEW_drift` as explicit blockers while file-level migration remains pending.
3. The post-Wave25 docs-root topic-local evidence files must be cited by the shared navigation surfaces before docs-root can be treated as navigation-clean.

Default audit mode reports the blocker without failing ordinary worker validation:

```bash
python3 scripts/checkers/check_docs_root_navigation_drift.py
```

Closure mode is for the supervisor/integration lane:

```bash
python3 scripts/checkers/check_docs_root_navigation_drift.py --require-clean
```

That mode should remain failing until shared navigation and `MERGED_OVERVIEW.md` cite the latest topic-local docs-root evidence and the content plan has no remaining unsafe or decomposed broad-move queues.

Observed audit summary in this worker branch:

```text
OK docs_root_navigation_drift=audit status=blocked surfaces=4 anchors=8 missing_refs=22 unsafe_moves=0 decomposed_moves=1
```

Observed closure-mode summary:

```text
FAIL docs_root_navigation_drift=audit status=blocked surfaces=4 anchors=8 missing_refs=22 unsafe_moves=0 decomposed_moves=1
```

## Closure Decision

Docs-root cannot close in Wave29 worker B.

The remaining blockers are repo-local, not external-runtime blockers:

- source archive compatibility shim conversion remains pending as per-file batch work;
- shared navigation still needs a supervisor-owned sync pass;
- `development/latest-dev-docs/MERGED_OVERVIEW.md` still needs a synchronized docs-root update.

The next closing lane should update the shared indexes and `MERGED_OVERVIEW.md` together with source shim conversion, then rerun:

```bash
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/checkers/check_docs_root_navigation_drift.py --require-clean
python3 scripts/check_current_dev_status_evidence.py
```
