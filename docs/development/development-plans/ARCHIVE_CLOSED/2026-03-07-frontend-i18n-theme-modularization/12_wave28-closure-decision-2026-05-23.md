<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/12_wave28-closure-decision-2026-05-23.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/12_wave28-closure-decision-2026-05-23.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Wave28 Frontend I18N / Theme Closure Decision

Date: 2026-05-23

Worker: Wave28 frontend worker B

Scope: `2026-03-07-frontend-i18n-theme-modularization` only.

## Decision

decision: `closed`

Archive target: `ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization`

The first-wave frontend i18n/theme/module platform contract is closed. The remaining business-string and page-shell work is not an independent blocker for this directory; it belongs to the active successor lane `CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite`.

This is not an `external_blocked` decision because the residual work is repo-local implementation breadth, not an external runtime, live tenant, public replay, or operator-review dependency. It is also not a `retired` decision because the platform plan was implemented and verified rather than invalidated by current code facts.

## Current Evidence

Commands observed in this wave:

```bash
npm --prefix main/frontend-modern run -s check:i18n-page-shell-disjoint
npm --prefix main/frontend-modern run -s check:topology-platform
npm --prefix main/frontend-modern run -s check:business-string-audit
```

Key readback:

```json
{
  "i18n_page_shell_disjoint": {
    "status": "ok",
    "frontend_i18n_platform_closed": true,
    "dual_frontend_can_transfer_to_three_layer": true,
    "page_shell_retirement_complete": false,
    "three_layer_retains_page_shell_blocker": true
  },
  "topology_platform": {
    "status": "ok",
    "modules": 31,
    "manifest_entries": 31,
    "i18n_locales": ["zh-CN", "en-US"],
    "themes": ["light", "dark", "brand"],
    "failures": []
  },
  "business_string_audit": {
    "status": "ok",
    "full_business_string_migration_complete": false,
    "remaining_migration_gaps_total": 1886,
    "failures": []
  }
}
```

Interpretation:

- i18n catalog, locale store, settings locale control, shell/layer-shell consumers, theme store, theme tokens, module manifest, and navigation/title consumption are covered by static gates.
- `check:i18n-page-shell-disjoint` explicitly separates i18n platform closure from page-shell retirement.
- The remaining page-shell blockers are still visible in `FrontendKernelApp`, `AppShell`, `FigmaSideNav`, and `routes`, but the checker assigns them to the three-layer rewrite lane.
- The business-string audit remains green as an inventory gate, not a closure gate; its remaining gaps are the input backlog for three-layer rewrite batches.

## Transferred Work

Do not reopen this directory for ordinary page-level i18n slices. Continue the remaining work under:

- `CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/README.md`
- `CURRENT_DEV/2026-03-15-frontend-three-layer-rewrite/13_wave21-frontend-i18n-closure-priority-2026-05-22.md`

Successor responsibilities:

- migrate remaining business strings by concentrated page batches rather than one-off evidence slices;
- retire the compatibility `AppShell` path only through the three-layer rewrite acceptance path;
- keep `check:business-string-audit` and `check:i18n-page-shell-disjoint` as guardrails while reducing the backlog.

## Closure Boundary

Closed in this directory:

- shell/shared i18n entrypoint and catalog anchors;
- locale persistence and settings control;
- theme enum, persistence, token groups, and shell token application;
- module manifest and navigation/title metadata contract;
- explicit transfer boundary for business-string and page-shell work.

Not claimed here:

- full business-content localization across all pages;
- page-shell retirement;
- full three-layer rewrite closure.
