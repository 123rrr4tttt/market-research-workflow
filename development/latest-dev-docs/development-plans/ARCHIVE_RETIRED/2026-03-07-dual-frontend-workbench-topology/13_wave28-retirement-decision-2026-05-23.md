# Wave28 retirement decision - Dual Frontend Workbench Topology

Date: 2026-05-23

Worker: Wave28 frontend worker A

Scope: `2026-03-07-dual-frontend-workbench-topology` only.

## Decision

decision: `retired_into_three_layer_rewrite`

The dual-frontend workbench topology topic no longer has an independent repo-local blocker. It should not remain in `CURRENT_DEV` as a separate partial directory.

This is not a full frontend closure claim. The remaining work is inherited by the active three-layer rewrite lane:

- page-shell retirement remains open;
- `AppShell` remains a compatibility/runtime path;
- full business-string migration remains broad;
- full page refactor acceptance remains false.

Current implementation work should continue through [`CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite`](../../CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/README.md). This archived directory is retained only as historical topology evidence and should not be used as a standalone implementation entry.

## Evidence

Wave27 split the ownership boundary with the i18n/page-shell disjoint gate:

- [`12_wave27-i18n-page-shell-disjoint-gate-2026-05-23.md`](./12_wave27-i18n-page-shell-disjoint-gate-2026-05-23.md)
- decision: `can_transfer_to_three_layer`
- `dual_frontend_unique_blocker`: `false`
- `dual_frontend_can_transfer_to_three_layer`: `true`
- `frontend_i18n_platform_closed`: `true`
- `three_layer_retains_page_shell_blocker`: `true`

The topology and layer-shell gates provide the repo-local closure basis:

- [`03_wave8-4-topology-i18n-theme-contract-evidence-2026-05-22.md`](./03_wave8-4-topology-i18n-theme-contract-evidence-2026-05-22.md)
- [`04_wave11-layer-shell-topology-contract-evidence-2026-05-22.md`](./04_wave11-layer-shell-topology-contract-evidence-2026-05-22.md)
- `check:topology-platform`: `status=ok`
- `check:layer-shell-contract`: `status=ok`

The business-string audit remains evidence for the successor blocker, not for keeping this directory open:

- [`05_wave12-frontend-business-string-audit-evidence-2026-05-22.md`](./05_wave12-frontend-business-string-audit-evidence-2026-05-22.md)
- `check:business-string-audit`: `status=ok`
- `full_business_string_migration_complete`: `false`

## Archive classification

Archive: `ARCHIVE_RETIRED`

Reason:

- `closed` would overstate the state of the full frontend rewrite.
- `external_blocked` would be incorrect because the remaining blocker is not an external runtime or production-data condition.
- `retired` is the precise state: this topic has been superseded by the three-layer rewrite lane, and keeping it as a separate `partial` entry duplicates the same inherited blockers.

## Follow-up owner

All remaining implementation should be tracked under:

- [`CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite`](../../CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/README.md)

Do not reopen this dual-frontend directory for page-shell retirement, `AppShell` retirement, broad business-string migration, or full page refactor acceptance. Those are successor-lane blockers.
