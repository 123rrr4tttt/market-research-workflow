# Modern-Based Dual-Interaction Frontend Topology Plan (2026-03-07)

> 日期：2026-03-07
> 范围：`main/frontend-modern` 内的 dual-interaction topology planning
> 状态：planning document, used to freeze scope, baseline, topology recommendation, and delivery order

## 1. Goal

This topic exists to define a modern-only frontend topology that separates:

1. high-interaction workbench surfaces;
2. lower-interaction management surfaces; and
3. the shared platform layer they must still reuse.

This is not a legacy coexistence plan. The practical outcome of this document is a clear answer to four questions:

- which current pages behave like workbenches vs management screens;
- which capabilities must stay shared across both surfaces;
- how navigation and context switching should work;
- in what order the topology should be introduced without overcommitting to a premature shell split.

## 2. Current Baseline

### 2.1 Active frontend baseline

The current active UI code is concentrated in `main/frontend-modern`.

Observed anchor files:

- `main/frontend-modern/src/app/shell/AppShell.tsx`
- `main/frontend-modern/src/app/navigation/index.ts`
- `main/frontend-modern/src/components/FigmaSideNav.tsx`

Practical implication:

- the project already has one active modern shell;
- there is no second active frontend application root under `main/` that can be treated as an already-existing peer frontend;
- therefore, "dual frontend" must currently be interpreted as topology and interaction-surface planning, not as a claim that two production frontend apps already exist.

### 2.2 Current navigation model

The current shell already exposes a stable `NavMode -> hash` mapping and a single side navigation tree.

Observed characteristics from the current implementation:

- navigation is grouped by function buckets such as overview, data, graph, flow, and system;
- grouping is not yet based on interaction surface;
- `parseLegacyHashToMode(...)` normalizes several historical hashes into the current modern modes;
- `flowLlmNodeDesign` is already treated specially and opens as a separate tab/window, which is a useful precedent for immersive workbench handling.

This means the repo already has:

- one shell;
- one navigation contract;
- one deep-link normalization layer.

What it does not yet have is an explicit workbench-vs-management topology contract.

### 2.3 Observed page shapes

The current page inventory already shows two clearly different interaction patterns.

Workbench-heavy pages already exist:

- `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - imports dedicated writing components such as `MarkdownEditor`, `MarkdownPreview`, `KeywordInsightSidebar`, `LlmAssistantPanel`, and `TemplateLibraryPanel`;
  - keeps long-lived editing state, panel state, and citation state;
  - clearly behaves like an immersive workspace.
- `main/frontend-modern/src/pages/GraphPage.tsx`
  - imports graph renderers, graph hooks, topology helpers, and visual state modules;
  - supports multi-mode visualization and editing-oriented graph interaction;
  - clearly behaves like a high-interaction canvas.
- `main/frontend-modern/src/pages/LlmDesignerPage.tsx`
  - is already routed through a special standalone opening path from `AppShell`;
  - should be treated as a workbench-oriented designer surface unless future evidence proves otherwise.

Management-heavy pages also already exist:

- `main/frontend-modern/src/pages/ProjectsPage.tsx`
- `main/frontend-modern/src/pages/CrawlerManagePage.tsx`
- `main/frontend-modern/src/pages/SettingsPage.tsx`
- `main/frontend-modern/src/pages/ResourcePage.tsx`
  - list, filter, form, recommendation, sync, and save actions dominate the interaction;
  - the page currently behaves more like an operations console than a long-lived workbench.
- `main/frontend-modern/src/pages/ProcessPage.tsx`
  - task list, status refresh, detail panels, and cancellation actions dominate the interaction;
  - the page is transactional and status-oriented.
- `main/frontend-modern/src/pages/DashboardPage.tsx`
  - KPI cards, tables, and refresh are the main behaviors;
  - the page is overview-oriented, not workbench-oriented.

### 2.4 Baseline gaps

The current baseline is usable, but the topology is still implicit.

Current gaps:

- workbench pages and management pages sit inside one navigation hierarchy without a frozen interaction model;
- page placement rules are not written down, so new pages can drift between categories;
- shared platform capabilities vs surface-specific container behavior are not separated clearly;
- context retention rules are not documented;
- the project has immersive pages, but not a documented definition of when they should stay inside the common shell vs when they deserve a more specialized container.

## 3. Requirement Clarification

### 3.1 What "dual-interaction frontend" means in this topic

For this topic, dual-interaction frontend means:

- one modern technology baseline;
- two interaction surfaces with different UX density and context behavior;
- one shared platform layer underneath;
- optional future shell/container divergence, but not a required split on day one.

It does not mean:

- reactivating a legacy frontend;
- reintroducing a dual-codebase migration plan;
- committing up front to two separately deployed frontend apps.

### 3.2 Primary user situations this topology must support

This topology must cover at least two stable user situations:

1. immersive work sessions
   - writing, graph editing, workflow design, deep analysis;
   - long-lived context, multi-panel coordination, object-level focus, higher information density.
2. operational management sessions
   - project setup, crawler control, resource maintenance, settings, process tracking;
   - shorter transactional actions, clearer lists/forms, stronger predictability.

### 3.3 Decisions that must be frozen in this round

This round must freeze:

- the classification rubric;
- the initial placement of current major pages;
- the shared platform layer;
- the navigation and context-switch rules;
- the phased rollout order.

This round must not pretend to freeze:

- final visual design;
- final workbench shell implementation;
- page-internal business requirements for writing, graph, or ingest domains.

## 4. Scope and Non-Goals

### 4.1 In scope

- a modern-only definition of workbench surfaces vs management surfaces;
- a page placement matrix for current major `frontend-modern` pages;
- the shared platform contract both surfaces must reuse;
- navigation and context-switch rules between the two surfaces;
- a phased implementation order that other topic folders can reference.

### 4.2 Out of scope

- legacy frontend migration strategy;
- a separate deployment architecture for multiple frontend apps;
- detailed feature design for writing, graph, ingest, or crawler domains;
- final UI comps or CSS specifications;
- backend API redesign unrelated to topology boundaries.

## 5. Recommended Topology

### 5.1 Layered model

The recommended model is a three-layer topology.

#### Layer A: Shared platform layer

This layer must remain unified:

- active project context and project switching;
- auth, permission, and user/session assumptions;
- route normalization and deep-link conventions;
- API client, query key families, cache policy, and error envelope expectations;
- theme and i18n foundations;
- global notification, loading, and failure conventions.

#### Layer B: Management surface

This surface should optimize for:

- predictable navigation;
- stable page layout;
- list/filter/form workflows;
- short transactional actions;
- lower cognitive switching cost.

Typical examples today:

- `ProjectsPage`
- `CrawlerManagePage`
- `ResourcePage`
- `SettingsPage`
- `ProcessPage`
- `DashboardPage`

#### Layer C: Workbench surface

This surface should optimize for:

- longer-lived object context;
- multi-panel or canvas-based interaction;
- higher information density;
- faster iteration inside one page;
- optional immersive or standalone container behavior where justified.

Typical examples today:

- `WritingWorkbenchPage`
- `GraphPage`
- `LlmDesignerPage`

### 5.2 Classification rubric

Pages should be classified using the rubric below.

| Dimension | Management signal | Workbench signal |
| --- | --- | --- |
| Interaction density | list/form/filter actions dominate | continuous editing or canvas actions dominate |
| Context continuity | page can be revisited briefly with little warm-up | user must stay in-context for long sessions |
| Panel coordination | one main content area is sufficient | multiple synchronized panels or tool regions are needed |
| State coupling | local transient state is light | page-local state is deep and affects multiple subareas |
| Primary outcome | configure, submit, inspect, monitor | create, edit, compare, design, synthesize |

Rule of use:

- classify by dominant user task, not by historical route name;
- if a page has strong signals on both sides, keep it in the lower-risk surface for phase 1 and record the reason;
- only promote a page to workbench when immersive context is a first-order requirement, not just a nice-to-have.

### 5.3 Initial page placement matrix

The first-pass placement for the current major pages should be:

| Page | Surface | Reason |
| --- | --- | --- |
| `WritingWorkbenchPage` | workbench | editing-heavy, multi-panel, long-lived context |
| `GraphPage` | workbench | canvas interaction, graph state, analysis/editing focus |
| `LlmDesignerPage` | workbench | designer workflow and existing standalone launch precedent |
| `ProjectsPage` | management | project setup and administrative task flow dominate |
| `CrawlerManagePage` | management | operations/configuration workflow dominates |
| `SettingsPage` | management | configuration-first and predictable layout preferred |
| `ResourcePage` | management-primary | current implementation is list/filter/form heavy; revisit only if a dedicated research asset workbench emerges |
| `DashboardPage` | management | read-mostly overview and KPI inspection |
| `ProcessPage` | management | queue/status/detail monitoring is transactional and operational |
| `OpsPage` | management | overview/admin behavior fits the management side |
| `IngestPage` | management-primary | ingestion operations and execution control dominate phase-1 behavior |
| `RawDataPage` | management-primary | processing workflow exists, but the current user task is still operational handling rather than immersive design |

Pages that may deserve later re-evaluation:

- `ResourcePage`: only if it grows a research-side evidence exploration mode;
- `IngestPage` / `RawDataPage`: only if they gain design-canvas or multi-stage orchestration behavior;
- `ProcessPage`: only if it evolves from monitoring into workflow design.

### 5.4 Navigation expression

Recommended phase-1 information architecture:

- keep one shared modern codebase and one platform layer;
- introduce an explicit first-level distinction between `Workbench` and `Management`;
- keep existing route hashes working during the first transition;
- avoid a hard shell split until placement, context rules, and shared contracts are stable.

Recommended navigation behavior:

- `Workbench`
  - graph
  - writing
  - llm designer
- `Management`
  - projects
  - crawler
  - resource
  - process
  - dashboard
  - settings

This recommendation does not require replacing the current shell immediately. It freezes the user-facing topology first, then allows shell/container changes afterward.

### 5.5 Context retention and switching rules

When switching between the two surfaces, the following rules should apply.

Retain across surfaces:

- active `projectKey`;
- authenticated identity and permission state;
- theme and locale;
- deep-link-compatible route identity when explicitly encoded in URL/hash;
- global notifications and error semantics.

Reset or narrow by default across surfaces:

- page-local selection state;
- temporary editor state that is not persisted by the page itself;
- transient comparison objects;
- panel open/close state unless the destination surface defines a compatible persistence rule.

Important design constraint:

- shared platform contract does not imply identical shell behavior;
- a workbench page may stay inside the common shell, open in a more immersive container, or launch standalone if the interaction demands it;
- the current `flowLlmNodeDesign` special handling is evidence that immersive exceptions are already acceptable.

### 5.6 Shared vs surface-specific ownership

Shared ownership:

- project activation and project-aware query scoping;
- route parsing and deep-link normalization;
- API client and query/cache conventions;
- theme/i18n primitives;
- global loading/error/notification conventions.

Surface-specific ownership:

- side navigation grouping and second-level navigation expression;
- panel layout density;
- page-local draft persistence and local object focus behavior;
- toolbars, side inspectors, and split-view behavior;
- immersive window or standalone launch logic where justified.

## 6. Implementation Order

### Phase 1: Freeze topology and placement

Deliverables:

- one approved classification rubric;
- one page placement matrix for current modern pages;
- one shared-platform vs surface-specific boundary list;
- one explicit statement that this topic is modern-only.

Purpose:

- remove ambiguity before shell or route changes begin.

### Phase 2: Introduce navigation and switching contract

Deliverables:

- first-level `Workbench` / `Management` navigation expression;
- documented retain/reset behavior when crossing surfaces;
- explicit guidance on when a page stays in the common shell vs uses an immersive container.

Purpose:

- make the topology visible to users without forcing a premature large refactor.

### Phase 3: Apply the topology to page containers

Deliverables:

- workbench-priority container upgrades for writing, graph, and llm designer;
- management-priority stabilization for project, crawler, resource, process, dashboard, and settings pages;
- a migration checklist for pages that may later change category.

Purpose:

- turn the topology into implementation work packages while keeping page placement stable.

## 7. Serial and Parallel Relations

Serial dependencies:

1. freeze terminology and scope;
2. freeze the baseline inventory;
3. freeze classification rules;
4. freeze page placement;
5. freeze shared-platform ownership;
6. freeze navigation and context-switch rules;
7. freeze phased rollout and validation.

Parallelizable work after the baseline inventory is stable:

- page classification criteria can be refined in parallel with shared-platform boundary drafting;
- navigation expression can be drafted in parallel with phased rollout planning once placement and shared ownership are frozen;
- later page-level implementation packages can proceed in parallel only after the topology contract is stable.

Future implementation conflict rule:

- any work that changes `AppShell.tsx`, `FigmaSideNav.tsx`, or `navigation/index.ts` should be serialized by task ID;
- page-local container changes for `WritingWorkbenchPage`, `GraphPage`, and `LlmDesignerPage` can run in parallel only if they do not rewrite the same shell/navigation files.

## 8. Minimal Validation

Structural validation for this plan:

1. Confirm the baseline page inventory still matches the repo:
   - `rg --files main/frontend-modern/src/pages`
2. Confirm the navigation contract is still anchored in one modern shell:
   - `rg -n "type NavMode|const groups|hashByMode|parseLegacyHashToMode" main/frontend-modern/src/components/FigmaSideNav.tsx main/frontend-modern/src/app/navigation/index.ts`
3. Confirm the shell still mounts the pages referenced in this plan:
   - `rg -n "WritingWorkbenchPage|GraphPage|LlmDesignerPage|ProjectsPage|CrawlerManagePage|ResourcePage|ProcessPage|DashboardPage|SettingsPage" main/frontend-modern/src/app/shell/AppShell.tsx`

Process validation for future implementation:

1. pick one workbench page and verify it keeps project context while changing page-local state;
2. pick one management page and verify it remains usable with predictable list/form flow;
3. verify cross-surface switching preserves `projectKey` but does not leak page-local transient state;
4. run `cd main/frontend-modern && npm run -s lint` after any topology-related code change.

## 9. Risks and Open Questions

Current risks:

- if placement rules stay vague, future pages will keep mixing workbench and management behaviors in the same hierarchy;
- if shared platform ownership is not frozen, each surface may rebuild its own project context, route parsing, or query conventions;
- if navigation shows no first-level distinction, users will not understand why some pages feel immersive and others feel transactional.

Open questions intentionally left for follow-up work, not for this document to overclaim:

- whether `ResourcePage` should later grow a separate research-oriented workbench mode;
- whether `IngestPage` or `ProcessPage` should remain management-only after workflow design capabilities expand;
- whether the workbench surface eventually deserves a distinct container family while still reusing the same platform layer.
