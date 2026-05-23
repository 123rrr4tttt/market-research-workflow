# Wave34 Docs Root Physical Archive

Date: 2026-05-23

## Result

`2026-03-07-docs-root-restructuring` is no longer physically present under
`development/latest-dev-docs/development-plans/CURRENT_DEV`.

The topic files moved to:

- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/`

The closure decision did not change: Wave31 had already cleared the docs-root
navigation and content-plan gates. This batch removes the remaining physical
location drift where `CURRENT_DEV/INDEX.md` marked the topic `clear_closed`
while the topic directory still lived under `CURRENT_DEV`.

## Gate Hardening

`scripts/check_current_dev_status_evidence.py` now fails when a direct
`CURRENT_DEV` topic directory is not backed by an active status row. This keeps
future `clear_closed` or `retired` topics from silently remaining in the active
tree.

## Verification

```bash
python3 scripts/check_current_dev_status_evidence.py --root .
python3 scripts/checkers/check_docs_root_navigation_drift.py --require-clean --verbose
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/check_latest_dev_docs_structure.py --root development/latest-dev-docs --link-path development/latest-dev-docs/README.md --link-path development/latest-dev-docs/MERGED_OVERVIEW.md --link-path development/latest-dev-docs/development-plans/INDEX.md --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md --link-path development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/INDEX.md
```
