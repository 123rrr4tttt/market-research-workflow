<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-frontend-i18n-theme-modularization/01_frontend-i18n-theme-modularization-plan-2026-03-07.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Frontend I18N, Theme, and Modularization Plan (2026-03-07)

> Date: 2026-03-07
> Scope: `main/frontend-modern`
> Status: 2026-05-23 closed; shell-level i18n/theme/module contracts are implemented and statically gated
> Constraint: keep the plan aligned with the current `main/frontend-modern` entrypoints instead of inventing a second frontend shell

## 0.1 2026-05-23 Closure Decision

Wave28 closes this directory as the first-wave frontend i18n/theme/module platform lane. The remaining business-string migration and page-shell retirement backlog is explicitly transferred to `ARCHIVE_CLOSED/2026-03-15-frontend-three-layer-rewrite`.

Closure decision: [12_wave28-closure-decision-2026-05-23.md](./12_wave28-closure-decision-2026-05-23.md)

## 0. 2026-05-22 Current Status Refresh

This topic is no longer only a planning document. The first-wave infrastructure described here has landed in current source:

- i18n catalog and translation access: `main/frontend-modern/src/app/platform/i18n/`
- locale persistence: `main/frontend-modern/src/app/platform/i18n/store.ts`
- theme persistence and token application: `main/frontend-modern/src/app/platform/theme/`
- shared storage keys and persisted store helper: `main/frontend-modern/src/app/platform/storageKeys.ts`, `main/frontend-modern/src/app/platform/state/createPersistedStore.ts`
- module descriptor registry: `main/frontend-modern/src/app/platform/modules/`
- canonical module manifest: `main/frontend-modern/src/app/kernel/moduleManifest.ts`
- settings controls for locale/theme: `main/frontend-modern/src/pages/SettingsPage.tsx`
- shell/nav consumers: `main/frontend-modern/src/app/shell/AppShell.tsx`, `main/frontend-modern/src/components/FigmaSideNav.tsx`

Validation evidence:

- [../../../automation-runs/frontend-topology-theme/2026-05-22/README.md](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md)

Current closure statement:

- Shell titles, navigation labels, settings labels, locale/theme persistence, module registry labels, and theme token groups are implemented and checked.
- Full business-content translation for every page remains out of scope for this topic and should not block the first-wave infrastructure closure.

## 1. Objective

This topic is the infrastructure layer for the modern frontend, not a one-off page polish pass.

The first implementation wave should make three cross-cutting capabilities explicit and reusable:

1. UI i18n for shell-level and shared frontend text.
2. Theme state plus a stable token boundary for shared UI surfaces.
3. Module registration so navigation, page mounting, and mode visibility are no longer maintained through scattered hardcoded branches.

The intended outcome is that later workbench pages and management pages can plug into one shared contract instead of each feature rebuilding its own shell behavior.

## 2. Verified Current Baseline

### 2.1 Active frontend surface

The active frontend base for this topic is `main/frontend-modern`.

The current shell path is already centralized:

- `main/frontend-modern/src/app/shell/AppShell.tsx`
- `main/frontend-modern/src/app/navigation/index.ts`
- `main/frontend-modern/src/components/FigmaSideNav.tsx`
- `main/frontend-modern/src/pages/SettingsPage.tsx`
- `main/frontend-modern/src/index.css`

This is the correct implementation seam for i18n, theme, and module registration work. The topic should not be framed as isolated page-by-page cleanup.

### 2.2 Reusable mechanisms already present

Several reusable patterns already exist in the current repo:

- `AppShell.tsx` already holds shell state such as `viewMode`, current project, shell-level health display, and lazy page mounting.
- `app/navigation/index.ts` already maps `NavMode` to hash routes and provides legacy-hash parsing. That makes route normalization a shared concern rather than a page-local concern.
- `FigmaSideNav.tsx` already defines grouped navigation and mode switching. It is the main candidate for shell-level label extraction.
- `lib/localStore.ts` already provides safe local storage helpers and is already used by `AppShell.tsx` and `SettingsPage.tsx`.
- `SettingsPage.tsx` already acts as a configuration surface and already persists local draft state, so it is a credible home for language/theme preferences.
- The modern frontend already contains both management-style pages and heavier interaction pages such as `GraphPage.tsx`, `WritingWorkbenchPage.tsx`, and `LlmDesignerPage.tsx`. That is enough evidence to plan around shared infrastructure for more than one interaction shape.

### 2.3 2026-05-22 resolved and residual gaps

The earlier baseline gaps above are now split into resolved first-wave infrastructure and residual architecture work.

Resolved in current source:

- shared frontend i18n catalog, locale store, and translation accessor exist under `main/frontend-modern/src/app/platform/i18n/`;
- `FigmaSideNav.tsx` reads groups and module labels from the module registry plus i18n keys;
- `AppShell.tsx` resolves page titles through `getModuleDescriptor(viewMode).titleKey`;
- theme is no longer fixed to a single local shell value; it is persisted through `useAppTheme`, `setAppTheme`, and settings controls;
- shared token groups are defined in `THEME_TOKENS` and applied through `applyThemeTokens(appTheme)`;
- navigation metadata now derives from `moduleManifest` through `platform/modules/registry.ts` and `kernel/legacyHashAdapter.ts`.

Residual work that remains outside this lane:

- page-level business content is not fully localized;
- some legacy CSS selectors still exist as compatibility styling, even though the shared token boundary exists;
- the old `AppShell` still participates in runtime shell orchestration and should be reduced in the broader three-layer rewrite closure;
- heavy page container/view splitting remains a three-layer rewrite follow-up, not an i18n/theme prerequisite.

## 3. Requirement Clarification

### 3.1 Target users and owners

This topic primarily serves:

- frontend engineers adding or modifying `main/frontend-modern` pages;
- feature owners who need shell-level language/theme behavior without re-implementing it;
- future workbench topics that need stronger interaction patterns but still depend on the same shell contract.

### 3.2 Problem statement

The core problem is not translation quality or color polish by itself.

The actual problem is that shell text, theme behavior, and module wiring are currently encoded in separate hardcoded locations. Without a shared contract:

- UI labels will continue to drift into component-local hardcoded strings;
- theme behavior will remain a mix of fixed state and CSS variants without clear ownership;
- every new mode will require touching multiple places by hand;
- workbench pages and standard admin pages will diverge in infrastructure even when they should share platform rules.

## 4. Scope and Non-Goals

### 4.1 In-scope for the first wave

The first wave should freeze and then implement only the minimum platform layer:

- shell-level locale state and locale persistence;
- shell/shared message catalog organization;
- theme enum, theme persistence, and shared token boundary;
- module registration metadata for navigation, page title, visibility, and hash mapping;
- settings entrypoints for language and theme preferences;
- onboarding rules for both standard pages and high-interaction pages.

### 4.2 Non-goals

This topic does not try to complete any of the following in the same wave:

- full translation of all business content across every page;
- backend-driven content localization or LLM language strategy;
- a full visual redesign of every existing page;
- replacement of all shell rendering logic in one step;
- a forced decision that every future interaction shape must share the exact same shell layout.

## 5. Recommended Architecture

### 5.1 Localization layer

Recommended direction: introduce a shell-owned locale contract first, then let pages consume that contract.

The first wave should define:

- one locale enum for UI display, initially scoped to `zh-CN` and `en-US` or an equivalent two-locale pair;
- one shell-level locale state source;
- one persistence rule using the existing local storage helper pattern;
- one translation access path for shell/shared text;
- one message catalog split that keeps shell text separate from domain-page text.

Recommended catalog partition for the first wave:

1. `shell`
   - app shell, page titles, common status text, generic buttons
2. `navigation`
   - group titles, nav item labels, route-facing mode names
3. `settings`
   - language/theme controls and related helper text
4. `shared`
   - reusable empty/loading/error text for common components

This document intentionally does not lock the repo to a specific third-party i18n runtime. The repo currently has no established frontend i18n stack, so the first decision should optimize for low-friction adoption in `main/frontend-modern`.

### 5.2 Theme layer

Recommended direction: keep theme ownership at shell scope first, but document a token contract instead of expanding ad hoc variant CSS.

The first wave should freeze:

- a stable theme enum;
- one theme state source;
- one persistence rule that survives refresh and mode switches;
- a minimum shared token contract for shell surfaces;
- rules for page-local extensions that do not redefine global shell semantics.

Minimum token groups for the first wave:

- background
- surface
- border
- text
- muted text
- accent
- status or emphasis
- interactive hover/focus/active

The important design decision is not the exact token names; it is the boundary. Shared shell surfaces should consume shared tokens, while page-local workbench styling may extend them without forking the global contract.

### 5.3 Module registration layer

Recommended direction: introduce module metadata as the shared source for navigation, page title, and visibility rules.

The minimum module registration object should be able to describe:

- `mode`
- `title_key`
- `nav_group_key`
- `hash`
- page loader or page component binding
- visibility flags
- interaction profile such as `standard` or `workbench`

This layer is needed because current behavior is split across:

- `hashByMode` in `app/navigation/index.ts`
- grouped navigation metadata in `FigmaSideNav.tsx`
- page title mapping in `AppShell.tsx`
- the page rendering `if` chain in `AppShell.tsx`

The first wave does not have to eliminate every branch immediately, but it should establish one registration contract that later refactors can converge toward.

### 5.4 Dual-interaction boundary

For this topic, “dual interaction” should mean:

- standard admin/dashboard flows and high-interaction workbench flows share language, theme, and module metadata contracts;
- they may still diverge in layout density, local controls, or workbench-specific interaction shells.

This topic should therefore define shared infrastructure, not force all pages into one identical presentation model.

## 6. Implementation Order

### 6.1 Stage 0: Freeze baseline and contracts

First freeze the current baseline and contract boundaries:

- inventory shell-visible strings;
- inventory current theme surfaces and variant classes;
- inventory all current `NavMode` definitions and where they are duplicated;
- confirm which state is already persisted through local storage.

This step is serial. Without it, later tasks will keep re-deriving different assumptions.

### 6.2 Stage 1: Introduce shell-level i18n and theme contracts

Once the baseline is frozen, define:

- locale state and persistence;
- theme state and persistence;
- message catalog partition;
- minimum theme token groups.

This stage should be implemented before migrating page-level consumers, because otherwise multiple pages will invent incompatible access patterns.

### 6.3 Stage 2: Introduce module registration metadata

After locale/theme contracts exist, define module registration metadata so shell text and navigation can consume translation keys and module descriptors from a common source.

This is the point where route metadata, page titles, navigation groups, and visibility rules should stop drifting independently.

### 6.4 Stage 3: Migrate shell entrypoints

Then migrate the highest-value shell surfaces first:

- `AppShell.tsx` page titles and shell messages;
- `FigmaSideNav.tsx` group titles and item labels;
- settings entrypoints for theme and locale controls.

This is the minimum user-visible slice that proves the infrastructure is real.

### 6.5 Stage 4: Onboard representative pages

After shell entrypoints are stable, onboard representative pages from both interaction shapes:

- one standard page path;
- one high-interaction page path.

The purpose is to verify that the infrastructure works across both simple and dense pages before larger-scale migration.

## 7. Serial and Parallel Relationships

### 7.1 Serial dependencies

The following order should remain serial:

1. Baseline freeze
2. Locale/theme contract freeze
3. Module registration contract freeze
4. Shell migration
5. Representative page onboarding
6. Regression closure

This order matters because module registration should consume translation/theme conventions, not invent them independently.

### 7.2 Safe parallel slices

Once Stage 0 is complete, some work can proceed in parallel:

- locale catalog partition and translation accessor design;
- theme token grouping and persistence design;
- module descriptor shape and visibility-rule design.

After those contracts are frozen, the following can also run in parallel:

- shell text migration in `AppShell.tsx`;
- navigation label migration in `FigmaSideNav.tsx`;
- settings integration for locale/theme controls.

### 7.3 File-conflict hotspots

The likely conflict hotspots are:

- `main/frontend-modern/src/app/shell/AppShell.tsx`
- `main/frontend-modern/src/app/navigation/index.ts`
- `main/frontend-modern/src/components/FigmaSideNav.tsx`
- `main/frontend-modern/src/pages/SettingsPage.tsx`
- `main/frontend-modern/src/index.css`

Any implementation plan that assigns multiple contributors to this topic should treat those files as serial merge points.

## 8. Minimal Validation

### 8.1 Structural validation

At minimum, later implementation must verify:

- a shell-visible string can be switched through the shared locale path;
- a theme switch changes shell surfaces through shared token usage rather than one-off class edits;
- one new or existing module can be represented through module metadata without adding yet another disconnected label map.

### 8.2 Flow validation

At minimum, later implementation must verify:

1. change language in the settings entrypoint;
2. refresh the page and confirm shell labels remain in the selected locale;
3. switch between at least two navigation modes and confirm locale/theme state remains stable;
4. open one standard page and one high-interaction page and confirm both still render under the same shell contract.

### 8.3 Minimum command-level check

If code changes are made for this topic, the minimum verification pack should include:

```bash
cd main/frontend-modern && npm run -s lint
```

If a lightweight frontend smoke script exists later, it should be added on top of lint rather than replacing the structural checks above.

## 9. Risks and Open Questions

### 9.1 Main risks

- If locale state is introduced without first extracting shell strings, the app will end up with mixed translated and hardcoded shell surfaces.
- If theme work only adds toggles without a token boundary, workbench pages will fork visual semantics immediately.
- If module registration is postponed too long, every new mode will keep expanding hardcoded maps and `if` chains.
- If high-interaction pages are ignored during onboarding, the resulting infrastructure may fit dashboards but fail on workbench-style screens.

### 9.2 Open questions to settle before implementation

- Should the first-wave locale preference remain frontend-local only, or later sync with project-level/user-level settings?
- Is `brand` a supported end-user theme in the first wave, or only an internal styling branch that should remain non-default?
- Do module visibility rules eventually need project-based or role-based gating, or is mode-level visibility enough for the first wave?
- Should page title generation be fully registration-driven immediately, or staged through a compatibility layer while the current `if` rendering chain remains in place?
