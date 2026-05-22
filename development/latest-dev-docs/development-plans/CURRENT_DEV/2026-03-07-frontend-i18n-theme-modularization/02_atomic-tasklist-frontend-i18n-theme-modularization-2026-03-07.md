# Atomic Task List: Frontend I18N, Theme, and Modularization (2026-03-07)

## Execution Status Snapshot

- 2026-05-22 status: `A1-A8` are implemented for the first-wave shell/platform scope. Locale, theme, module registration, shell title consumption, navigation label consumption, and settings controls are present in source.
- `A9` is contract-covered rather than full-page localized: the static gate verifies shell/nav/module contracts across all registered modes; full business-content localization remains out of scope.
- `A10` now has a repeatable minimum gate: `npm --prefix main/frontend-modern run check:topology-platform`, plus `npm --prefix main/frontend-modern run lint`.
- Evidence: [../../../automation-runs/frontend-topology-theme/2026-05-22/README.md](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md).
- Residual work: reduce old shell orchestration and split heavy pages in the three-layer rewrite lane; do not treat missing full business-content localization as a blocker for this platform contract.

## Global Serial-Parallel Rules

- `L0` serial bootstrap: `A1` must complete first. No implementation task should redefine the baseline after this point.
- `L1` parallel foundations: `A2`, `A3`, and `A4` can run in parallel once `A1` is frozen.
- `L2` serial integration package: `A5` depends on `A2-A4` and converts the three contracts into one shell integration plan.
- `L3` parallel shell migration: `A6`, `A7`, and `A8` can run in parallel after `A5`, with file-conflict rules enforced.
- `L4` serial onboarding and closure: `A9` then `A10`.

File-conflict rule:

- tasks touching `main/frontend-modern/src/app/shell/AppShell.tsx` must run serially;
- tasks touching `main/frontend-modern/src/app/navigation/index.ts` must run serially;
- tasks touching `main/frontend-modern/src/components/FigmaSideNav.tsx` must run serially;
- tasks touching `main/frontend-modern/src/pages/SettingsPage.tsx` must run serially;
- tasks touching `main/frontend-modern/src/index.css` must run serially.

## Global Module Boundary Rules

The implementation should keep five module boundaries explicit:

- shell state boundary
  - `AppShell.tsx`, shell-local storage keys, shell-level mode/title behavior
- navigation boundary
  - `FigmaSideNav.tsx`, nav grouping, visible mode labels, mode-switch entrypoints
- routing and registry boundary
  - `app/navigation/index.ts`, `NavMode`, hash mapping, registration metadata
- settings boundary
  - `SettingsPage.tsx`, locale/theme user controls, persistence entrypoints
- presentation boundary
  - `index.css`, `FigmaTopNav.tsx`, `FigmaSideNav.tsx`, shared shell surfaces consuming theme tokens

Any task that crosses more than one boundary must state why the cross-boundary coupling is necessary.

## Global IO Contract

Each implementation task should explicitly describe:

- `module_input_vars`
  - `in_*` values, types, and source files
- `module_output_vars`
  - `out_*` values, types, and consuming files
- `io_mapping`
  - how the task transforms or wires `in_*` to `out_*`
- `io_boundary`
  - allowed read/write scope

This topic is infrastructure work. A task is incomplete if it changes UI behavior without documenting the state and contract it introduced.

## Task A1: Freeze Verified Baseline and String Inventory

- Goal: produce one verified baseline for current locale, theme, route, and shell text ownership in `main/frontend-modern`.
- status: pending
- depends_on: `[]`
- blocks: `["A2","A3","A4"]`
- Input:
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/frontend-modern/src/pages/SettingsPage.tsx`
  - `main/frontend-modern/src/index.css`
- Output:
  - one baseline summary
  - one shell-visible string inventory
  - one duplicated-metadata inventory for mode, title, and route definitions
- Acceptance:
  - clearly identifies current hardcoded shell labels and titles;
  - clearly identifies where theme state exists and where it is still fixed;
  - clearly identifies where `NavMode`, hash mapping, and page mounting are duplicated.
- Minimum validation:
  - repo read-through completed for the listed files;
  - no baseline statement contradicts current code.
- Module IO:
  - module_input_vars: `in_shell_files(files)`, `in_nav_files(files)`, `in_settings_file(file)`, `in_css_file(file)`
  - module_output_vars: `out_baseline(doc)`, `out_string_inventory(list)`, `out_duplication_map(list)`
  - io_mapping: `in_*` -> verified baseline and inventory artifacts
  - io_boundary: read current frontend shell files only

## Task A2: Define Locale Contract and Persistence Model

- Goal: freeze the first-wave locale model for shell and shared UI text.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A5","A6","A8","A9"]`
- Input:
  - `A1` baseline summary
  - shell-visible string inventory
  - `main/frontend-modern/src/lib/localStore.ts`
- Output:
  - one locale enum definition
  - one locale state owner definition
  - one persistence rule
  - one message catalog partition plan
- Acceptance:
  - defines who owns locale state;
  - defines how locale survives refresh and mode switch;
  - separates shell/navigation/settings/shared text from domain-page text;
  - does not claim business-content translation is in scope.
- Minimum validation:
  - one structural walkthrough showing locale selection path and read path;
  - one example mapping from hardcoded shell string to catalog key.
- Module IO:
  - module_input_vars: `in_shell_strings(list)`, `in_local_store(api)`, `in_current_modes(list)`
  - module_output_vars: `out_locale_state(obj)`, `out_locale_storage_rule(obj)`, `out_message_partitions(list)`
  - io_mapping: shell strings -> catalog partitions; locale selection -> persisted locale state
  - io_boundary: shell i18n contract only

## Task A3: Define Theme Contract and Token Boundary

- Goal: freeze the first-wave theme model and minimum token groups for shared shell surfaces.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A5","A7","A8","A9"]`
- Input:
  - `A1` baseline summary
  - current shell theme usage in `AppShell.tsx`, `FigmaSideNav.tsx`, `FigmaTopNav.tsx`, and `index.css`
- Output:
  - one theme enum and state-owner definition
  - one theme persistence rule
  - one minimum token-group contract
  - one shell-surface consumption map
- Acceptance:
  - defines supported first-wave themes;
  - defines where the theme state lives and how it persists;
  - defines minimum token groups for shell surfaces;
  - distinguishes shared tokens from page-local workbench extensions.
- Minimum validation:
  - one theme-switch walkthrough from settings entrypoint to shell surface;
  - one example showing shell styles consume tokens rather than one-off per-page overrides.
- Module IO:
  - module_input_vars: `in_theme_variants(list)`, `in_shell_components(files)`, `in_css_surfaces(list)`
  - module_output_vars: `out_theme_state(obj)`, `out_theme_tokens(list)`, `out_surface_map(list)`
  - io_mapping: theme selection -> shell theme state -> shared surface token usage
  - io_boundary: shared shell theme contract only

## Task A4: Define Module Registration and Visibility Contract

- Goal: introduce one registration model that can eventually drive route mapping, titles, navigation, and visibility.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A5","A6","A9"]`
- Input:
  - `A1` duplication map
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
- Output:
  - one module registration schema
  - one compatibility plan for current `NavMode` and `hashByMode`
  - one visibility-rule draft
- Acceptance:
  - registration schema includes mode, title key, nav group, hash, component binding, and interaction profile;
  - explains how current hardcoded maps can migrate incrementally;
  - distinguishes shared module metadata from page-local logic.
- Minimum validation:
  - one sample module definition for an existing mode;
  - one walkthrough showing how nav label and page title can read from the same registration source.
- Module IO:
  - module_input_vars: `in_modes(list)`, `in_hash_map(obj)`, `in_nav_groups(obj)`, `in_shell_mount_logic(code)`
  - module_output_vars: `out_module_schema(type)`, `out_registry_examples(list)`, `out_visibility_rules(list)`
  - io_mapping: current duplicated mode metadata -> normalized module registration contract
  - io_boundary: route and module metadata only

## Task A5: Freeze Shell Integration Plan

- Goal: turn the locale, theme, and module contracts into one concrete implementation package for the shell.
- status: pending
- depends_on: `["A2","A3","A4"]`
- blocks: `["A6","A7","A8"]`
- Input:
  - outputs of `A2-A4`
  - current shell entrypoints in `AppShell.tsx`, `FigmaSideNav.tsx`, `SettingsPage.tsx`, `index.css`
- Output:
  - one integration sequence for shell files
  - one ownership map by file
  - one backward-compatibility note for current route and render behavior
- Acceptance:
  - assigns clear ownership for shell state, settings control, and presentation layers;
  - identifies serial edit hotspots;
  - allows a staged migration instead of a big-bang rewrite.
- Minimum validation:
  - plan can be executed without requiring a same-step rewrite of every page;
  - no file is left without a clear owner or role.
- Module IO:
  - module_input_vars: `in_locale_contract(obj)`, `in_theme_contract(obj)`, `in_module_contract(obj)`, `in_shell_files(files)`
  - module_output_vars: `out_integration_plan(doc)`, `out_file_ownership(list)`, `out_compat_notes(list)`
  - io_mapping: three contracts -> concrete shell integration sequence
  - io_boundary: shell integration planning only

## Task A6: Migrate Shell and Navigation Text Consumption

- Goal: make shell titles, navigation labels, and shared shell text read from the locale contract instead of inline hardcoded strings.
- status: pending
- depends_on: `["A5"]`
- blocks: `["A9","A10"]`
- Input:
  - locale contract from `A2`
  - module contract from `A4`
  - `AppShell.tsx`
  - `FigmaSideNav.tsx`
- Output:
  - localized shell-title consumption path
  - localized navigation label consumption path
  - reduced duplication between title and nav metadata
- Acceptance:
  - `AppShell` no longer owns an isolated page-title label map;
  - `FigmaSideNav` no longer hardcodes the first-wave shell labels inline;
  - at least one shared metadata path is used by both shell title and navigation.
- Minimum validation:
  - switch locale and confirm page title plus navigation labels update together;
  - refresh and confirm locale is preserved.
- Module IO:
  - module_input_vars: `in_locale(str)`, `in_registry(obj)`, `in_mode(NavMode)`
  - module_output_vars: `out_title(str)`, `out_nav_groups(obj)`, `out_locale_synced(bool)`
  - io_mapping: locale + registry + mode -> shell title and nav labels
  - io_boundary: shell and nav text consumption only

## Task A7: Migrate Theme State, Persistence, and Shared Shell Surfaces

- Goal: replace the fixed shell theme behavior with a persisted shared theme path for shell surfaces.
- status: pending
- depends_on: `["A5"]`
- blocks: `["A9","A10"]`
- Input:
  - theme contract from `A3`
  - `AppShell.tsx`
  - `SettingsPage.tsx`
  - `index.css`
  - shell components receiving `theme` props
- Output:
  - theme selection state owned at shell scope
  - settings entrypoint for theme changes
  - shell surfaces aligned to shared token semantics
- Acceptance:
  - theme is no longer fixed to `'dark'`;
  - selected theme survives refresh and mode switches;
  - shell surfaces consume the shared theme model consistently.
- Minimum validation:
  - switch theme in settings and confirm shell surfaces update;
  - refresh and confirm theme remains selected.
- Module IO:
  - module_input_vars: `in_theme_selection(str)`, `in_theme_contract(obj)`, `in_shell_surfaces(list)`
  - module_output_vars: `out_theme_state(str)`, `out_persisted_theme(str)`, `out_surface_styles(list)`
  - io_mapping: settings theme input -> shell theme state -> shared shell surfaces
  - io_boundary: shell theme state and shell presentation only

## Task A8: Add Locale and Theme Controls to Settings Entry

- Goal: make `SettingsPage.tsx` the first user-facing control surface for locale and theme preferences.
- status: pending
- depends_on: `["A5"]`
- blocks: `["A9","A10"]`
- Input:
  - locale contract from `A2`
  - theme contract from `A3`
  - `main/frontend-modern/src/pages/SettingsPage.tsx`
  - `main/frontend-modern/src/lib/localStore.ts`
- Output:
  - one locale control path
  - one theme control path
  - one persistence handoff to shell state
- Acceptance:
  - settings page exposes locale and theme controls without conflicting with current settings content;
  - controls write to the agreed persistence path;
  - shell state reacts without requiring a full architecture rewrite.
- Minimum validation:
  - use settings page to change locale and theme;
  - confirm both values are visible after refresh.
- Module IO:
  - module_input_vars: `in_settings_event(event)`, `in_locale_contract(obj)`, `in_theme_contract(obj)`
  - module_output_vars: `out_locale_pref(str)`, `out_theme_pref(str)`, `out_shell_sync(bool)`
  - io_mapping: settings events -> persisted prefs -> shell sync
  - io_boundary: settings entrypoint only

## Task A9: Onboard Representative Standard and Workbench Pages

- Goal: prove the infrastructure works for both a standard page and a high-interaction page.
- status: pending
- depends_on: `["A6","A7","A8"]`
- blocks: `["A10"]`
- Input:
  - updated shell contracts
  - one representative standard page such as `DashboardPage.tsx` or `ProcessPage.tsx`
  - one representative workbench page such as `WritingWorkbenchPage.tsx` or `GraphPage.tsx`
- Output:
  - one standard-page onboarding result
  - one workbench-page onboarding result
  - one list of follow-up migration deltas
- Acceptance:
  - both page types render under the same locale and theme contract;
  - no page-specific workaround breaks shell consistency;
  - any remaining incompatibility is explicitly logged as follow-up work.
- Minimum validation:
  - navigate between the chosen standard page and workbench page;
  - confirm locale and theme remain stable in both.
- Module IO:
  - module_input_vars: `in_selected_pages(list)`, `in_shell_contracts(obj)`, `in_mode_switch(event)`
  - module_output_vars: `out_page_alignment_report(doc)`, `out_followups(list)`
  - io_mapping: selected pages + shell contracts -> onboarding proof and residual-gap list
  - io_boundary: one standard page and one workbench page only

## Task A10: Run Minimum Regression Pack and Close Risks

- Goal: close the first-wave implementation with a minimum regression and risk summary.
- status: pending
- depends_on: `["A9"]`
- blocks: `[]`
- Input:
  - outputs of `A6-A9`
  - frontend lint command
- Output:
  - one minimum regression result
  - one unresolved-risk log
  - one next-wave backlog seed
- Acceptance:
  - regression pack includes locale persistence, theme persistence, module navigation consistency, and dual-interaction smoke checks;
  - unresolved risks are explicit rather than implied;
  - follow-up work is separated from first-wave acceptance.
- Minimum validation:
  - `cd main/frontend-modern && npm run -s lint`
  - manual shell flow checks for locale/theme/module behavior
- Module IO:
  - module_input_vars: `in_lint_result(report)`, `in_shell_checks(list)`, `in_onboarding_report(doc)`
  - module_output_vars: `out_regression_summary(doc)`, `out_risk_log(list)`, `out_next_wave(list)`
  - io_mapping: lint + manual checks + onboarding proof -> closure summary and residual backlog
  - io_boundary: validation and documentation closure only
