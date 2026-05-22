# Atomic Task List: Modern-Based Dual-Interaction Frontend Topology (2026-03-07)

## Execution Status Snapshot

- 2026-05-22 status: `A1-A8` are contract-closed for the modern-only dual-interaction topology. The current implementation stores scope, baseline inventory, classification, page placement, shared platform boundary, navigation switching, and validation in source code.
- Evidence: [../../../automation-runs/frontend-topology-theme/2026-05-22/README.md](../../../automation-runs/frontend-topology-theme/2026-05-22/README.md).
- Current gate: `npm --prefix main/frontend-modern run check:topology-platform`.
- Residual work: do not reopen this topic as a legacy coexistence plan. Remaining UI architecture work belongs to the three-layer rewrite closure lane, especially `AppShell` retirement and heavy page container/view boundaries.

## Global Serial-Parallel Rules

- `L0` serial bootstrap: `A1` must finish first so later tasks do not drift back into legacy or dual-codebase semantics.
- `L1` serial evidence capture: `A2` must finish before any page-placement or platform-boundary decision is treated as stable.
- `L2` split decision layer:
  - `A3` classification rubric
  - `A5` shared-platform boundary
  These can run in parallel after `A2`, because both depend on the same baseline but produce different artifacts.
- `L3` topology synthesis:
  - `A4` depends on `A2 + A3`
  - `A6` depends on `A4 + A5`
- `L4` closure:
  - `A7` depends on `A4 + A5 + A6`
  - `A8` depends on `A7`

Future implementation conflict rule:

- any later implementation task touching `main/frontend-modern/src/app/shell/AppShell.tsx`, `main/frontend-modern/src/components/FigmaSideNav.tsx`, or `main/frontend-modern/src/app/navigation/index.ts` should run serially;
- page-local workbench container tasks may run in parallel only after the shell/navigation contract is frozen.

## Global Module Boundaries

| Module | Purpose | Read boundary | Output boundary |
| --- | --- | --- | --- |
| `topology-scope` | freeze terminology and planning boundary | current topic docs + planning rules | dual-interaction vocabulary, scope, non-goals |
| `baseline-inventory` | capture current modern shell and page evidence | `AppShell`, `navigation`, `FigmaSideNav`, page files | current-state inventory and observed interaction signals |
| `classification-rubric` | define workbench vs management decision rule | baseline inventory | reusable rubric and decision notes |
| `page-placement` | place current pages into surfaces | rubric + page evidence | placement matrix and hold/revisit notes |
| `shared-platform-contract` | freeze shared vs surface-specific capabilities | shell, route, query, context baseline | ownership boundary list |
| `navigation-switching` | define first-level IA and retain/reset rules | placement + shared boundary | topology-visible navigation and switching contract |
| `phase-rollout` | convert planning into delivery order | all prior modules | phase packages and dependency notes |
| `validation-baseline` | define minimum regression checks | all prior modules | minimal validation matrix |

## Task A1: Freeze Terminology and Scope

- 目标: Freeze the meaning of "dual-interaction frontend topology" so the topic stays modern-only and does not regress into legacy coexistence planning.
- status: pending
- depends_on: `[]`
- blocks: `["A2","A3","A4","A5","A6","A7","A8"]`
- 输入:
  - `development/latest-dev-docs/README.md`
  - `01_abstract-planning-folderization-plan-2026-03-07.md`
  - `01_dual-frontend-workbench-topology-plan-2026-03-07.md`
- 输出:
  - one frozen terminology note
  - one explicit scope list
  - one explicit non-goals list
- 验收:
  - the topic is defined as modern-only;
  - "dual frontend" is interpreted as two interaction surfaces, not two active codebases;
  - legacy coexistence, migration, or compatibility strategy is explicitly excluded.
- 最小验证:
  - re-read the main plan and ensure the scope/non-goal sections match this task output.
- 模块边界:
  - reads: planning docs only
  - writes: topology scope and vocabulary only

## Task A2: Capture Current Baseline Inventory

- 目标: Record the actual `frontend-modern` shell, navigation, route, and major page evidence before classifying anything.
- status: pending
- depends_on: `["A1"]`
- blocks: `["A3","A4","A5"]`
- 输入:
  - `main/frontend-modern/src/app/shell/AppShell.tsx`
  - `main/frontend-modern/src/app/navigation/index.ts`
  - `main/frontend-modern/src/components/FigmaSideNav.tsx`
  - `main/frontend-modern/src/pages/*`
- 输出:
  - one current-shell summary
  - one page inventory snapshot
  - one interaction-evidence note for high-interaction and management-heavy pages
- 验收:
  - inventory explicitly records the single active shell baseline;
  - inventory includes current hash-based navigation behavior;
  - inventory includes at least the major pages referenced by this topic.
- 最小验证:
  - `rg --files main/frontend-modern/src/pages`
  - `rg -n "type NavMode|const groups|hashByMode|parseLegacyHashToMode" main/frontend-modern/src/components/FigmaSideNav.tsx main/frontend-modern/src/app/navigation/index.ts`
- 模块边界:
  - reads: shell/navigation/page files
  - writes: baseline inventory only

## Task A3: Freeze the Classification Rubric

- 目标: Define a reusable rule set for deciding whether a page belongs to workbench or management surface.
- status: pending
- depends_on: `["A2"]`
- blocks: `["A4","A6","A7"]`
- 输入:
  - baseline inventory from `A2`
  - observed page behaviors
- 输出:
  - one classification rubric table
  - one rule-of-use note for ambiguous pages
- 验收:
  - rubric covers interaction density, context continuity, panel coordination, state coupling, and primary outcome;
  - rubric tells future authors how to handle mixed-signal pages;
  - rubric can be applied without relying on historical route names.
- 最小验证:
  - ensure every rubric dimension has both management and workbench signals.
- 模块边界:
  - reads: baseline inventory only
  - writes: classification rules only

## Task A4: Produce the Initial Page Placement Matrix

- 目标: Classify the current major `frontend-modern` pages using the frozen rubric instead of leaving them as informal examples.
- status: pending
- depends_on: `["A2","A3"]`
- blocks: `["A6","A7"]`
- 输入:
  - page inventory from `A2`
  - rubric from `A3`
- 输出:
  - one page placement matrix
  - one revisit list for pages that may later move surfaces
- 验收:
  - at minimum covers `GraphPage`, `WritingWorkbenchPage`, `LlmDesignerPage`, `ProjectsPage`, `ResourcePage`, `CrawlerManagePage`, `SettingsPage`, `DashboardPage`, and `ProcessPage`;
  - each page has a placement result and a short reason;
  - any "revisit later" page still gets a phase-1 placement instead of staying undefined.
- 最小验证:
  - `rg -n "WritingWorkbenchPage|GraphPage|LlmDesignerPage|ProjectsPage|CrawlerManagePage|ResourcePage|ProcessPage|DashboardPage|SettingsPage" main/frontend-modern/src/app/shell/AppShell.tsx`
- 模块边界:
  - reads: rubric + current page evidence
  - writes: placement matrix only

## Task A5: Define the Shared Platform Contract

- 目标: Freeze which capabilities must stay shared across both surfaces and which behaviors can be surface-specific.
- status: pending
- depends_on: `["A2"]`
- blocks: `["A6","A7"]`
- 输入:
  - shell/navigation baseline
  - page context behavior observed in `A2`
- 输出:
  - one shared-platform capability list
  - one surface-specific ownership list
- 验收:
  - shared list covers project context, route/deep-link normalization, API/query conventions, theme/i18n, and global loading/error/notification behavior;
  - surface-specific list covers container density, secondary navigation, panel layout, and immersive launch behavior;
  - the task explicitly states that shared contract does not mean identical shell UX.
- 最小验证:
  - verify each shared capability maps back to a real current anchor such as shell, route parsing, query keys, or page context handling.
- 模块边界:
  - reads: shell/navigation/context baseline
  - writes: ownership boundary only

## Task A6: Define Navigation and Context Switching

- 目标: Turn the topology into a visible user-facing model with first-level surface separation and explicit retain/reset rules.
- status: pending
- depends_on: `["A4","A5"]`
- blocks: `["A7","A8"]`
- 输入:
  - page placement matrix from `A4`
  - shared-platform contract from `A5`
  - current hash/navigation baseline
- 输出:
  - one first-level IA proposal
  - one retain/reset rule set for surface switching
  - one note on immersive or standalone exceptions
- 验收:
  - the proposal explicitly distinguishes `Workbench` and `Management`;
  - it states what survives a cross-surface switch, especially `projectKey`, theme, locale, and deep-link-compatible route identity;
  - it states what resets by default, especially page-local transient selection and panel state;
  - it records the current `flowLlmNodeDesign` standalone precedent without overclaiming a mandatory shell split.
- 最小验证:
  - `rg -n "flowLlmNodeDesign|window.open|hashByMode" main/frontend-modern/src/app/shell/AppShell.tsx main/frontend-modern/src/app/navigation/index.ts`
- 模块边界:
  - reads: placement + ownership + route baseline
  - writes: IA and switching contract only

## Task A7: Freeze the Phased Rollout and Work Packages

- 目标: Convert the topology decision into an executable phase order for later implementation topics.
- status: pending
- depends_on: `["A4","A5","A6"]`
- blocks: `["A8"]`
- 输入:
  - placement matrix
  - shared-platform contract
  - navigation/switching contract
- 输出:
  - one phase plan
  - one dependency note for related topics such as writing, graph, and frontend modularization
- 验收:
  - Phase 1 freezes rules and placement;
  - Phase 2 introduces navigation and switching visibility;
  - Phase 3 applies the topology to page containers and work packages;
  - the phase plan does not include legacy migration work.
- 最小验证:
  - re-check that the phase order in the main plan matches the dependency order in this task list.
- 模块边界:
  - reads: all prior topology decisions
  - writes: rollout plan only

## Task A8: Define the Minimal Validation Matrix

- 目标: Leave a small but reusable validation baseline so future implementation work can verify the topology without re-deriving checks from scratch.
- status: pending
- depends_on: `["A7"]`
- blocks: `[]`
- 输入:
  - frozen topology plan
  - phase rollout order
- 输出:
  - one minimal validation matrix
  - one structural command list
- 验收:
  - includes at least one workbench-page check;
  - includes at least one management-page check;
  - includes at least one cross-surface switching check;
  - includes at least one shared-platform reuse check;
  - includes at least one concrete repo command.
- 最小验证:
  - `rg --files main/frontend-modern/src/pages`
  - `cd main/frontend-modern && npm run -s lint`
- 模块边界:
  - reads: frozen topology outputs only
  - writes: validation matrix only
