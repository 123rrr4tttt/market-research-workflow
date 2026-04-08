# Writing Workbench Evolution Plan (2026-03-07)

> Date: 2026-03-07
> Scope: evolution plan for the existing writing workbench after the builtin workbench MVP baseline
> Status: planning document; intended to guide the next implementation split, not to restate implementation facts that are not visible in repo

## 1. Objective

This document is a follow-up to `2026-03-07-builtin-writing-workbench-design`, not a duplicate of it.

The builtin design document answered "what a writing workbench should contain." This evolution document answers a narrower and more important question: how the already-started writing domain should be converged into a stable primary workflow for research writing.

The target of this round is to make the workbench operationally coherent:

1. Freeze one primary writing loop that can remain stable while adjacent features evolve.
2. Clarify the responsibility split among document editing, evidence cards, graph context, templates, and LLM actions.
3. Keep Markdown as the canonical internal format while staging richer export requirements instead of letting them distort the core flow.
4. Define an execution order that matches the current repo reality, where the writing page and writing API already exist.

## 2. Current Baseline

### 2.1 Upstream document baseline

The immediate upstream references are:

- `development/latest-dev-docs/development-plans/ARCHIVE_RETIRED/2026-03-07-builtin-writing-workbench-design/01_builtin-writing-workbench-design-2026-03-07.md`
- `development/latest-dev-docs/development-plans/ARCHIVE_RETIRED/2026-03-07-builtin-writing-workbench-design/02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md`

Those documents are the historical MVP baseline for Markdown editing, preview, keyword cards, templates, and writing-oriented LLM actions.

This document should therefore focus on delta and convergence, not on re-proposing the same MVP from zero.

### 2.2 Visible repo baseline

The repo already contains a concrete writing-domain surface.

Frontend surface already exists:

- `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
- `main/frontend-modern/src/components/writing/MarkdownEditor.tsx`
- `main/frontend-modern/src/components/writing/MarkdownPreview.tsx`
- `main/frontend-modern/src/components/writing/KeywordInsightSidebar.tsx`
- `main/frontend-modern/src/components/writing/WritingInsightCard.tsx`
- `main/frontend-modern/src/components/writing/TemplateLibraryPanel.tsx`
- `main/frontend-modern/src/components/writing/LlmAssistantPanel.tsx`
- `main/frontend-modern/src/components/writing/CitationBasket.tsx`
- `main/frontend-modern/src/components/writing/useSelectionLookup.ts`

Backend contract and services already exist:

- `main/backend/app/api/writing.py`
- `main/backend/app/contracts/schemas/writing.py`
- `main/backend/app/services/writing/document_service.py`
- `main/backend/app/services/writing/citation_service.py`
- `main/backend/app/services/writing/keyword_card_service.py`
- `main/backend/app/services/writing/template_service.py`
- `main/backend/app/services/writing/llm_action_service.py`
- `main/backend/app/services/writing/search_suggest_service.py`

Capabilities already visible from those modules:

- document listing, create, read, patch, autosave, and version-conflict handling
- keyword-card search, preview, and detail fetch
- citation upsert/list flows
- template listing and validation
- LLM action dispatch, history, and detail lookup
- Markdown export with citation rebuild

### 2.3 Baseline gaps

The main problem is no longer "the writing domain does not exist." The real gap is that the existing surface is broad, but its main workflow is still under-defined.

Current gaps that matter for the next round:

- The primary user flow is not explicitly frozen. The page already combines editing, preview, templates, insights, citations, and LLM actions, but the authoritative order of use is not documented.
- Graph participation is implied by source types such as `graph`, but graph context is not yet positioned as an explicit, bounded writing-side interaction model.
- Template support exists, but the boundary between template-as-starter, template-as-variable-system, and template-as-workflow is still blurred.
- Markdown export exists, but non-Markdown export remains only a requirement direction and must not be treated as if it were already designed.
- The current page concentrates a large amount of state orchestration in `WritingWorkbenchPage.tsx`, which increases the risk of mixing future evolution topics into one component without a stable module split.

## 3. Requirement Clarification

### 3.1 Primary users and scenarios

The target users are analysts and research operators who need one place to turn evidence into narrative output.

The high-value scenarios are:

1. Open or create a document and keep writing without leaving the workbench.
2. Select text, pull evidence cards, inspect provenance, and turn the selection into cited material.
3. Run LLM actions on a selection or section without handing control of the whole document to the model.
4. Start from a template, but continue editing as a normal Markdown document instead of being trapped in a template-only flow.
5. Export the current document in a reproducible way after citations have been reconciled into the output.

### 3.2 What must be true in this round

This round should clarify the product contract, not simply add more UI.

Required outcomes:

- The workbench must have one explicit primary loop:
  - open or create document
  - edit Markdown
  - select text or place cursor in a target section
  - fetch supporting context
  - run a writing action
  - insert or reconcile the result back into the document
- Evidence context and graph context must not be merged into one vague "assistant" concept.
- Template usage must remain subordinate to document editing, not become a parallel authoring system.
- Export planning must preserve Markdown as the canonical internal source.

### 3.3 Constraints and assumptions

The following constraints are already visible or strongly implied by repo structure and should be treated as working assumptions:

- `project_key` scoping is part of the writing contract and must remain explicit.
- Markdown remains the canonical source inside the platform.
- LLM actions must preserve auditability through request or trace identifiers instead of becoming opaque local-only UI actions.
- Citation handling is part of the core writing loop, not an optional post-processing step.
- Graph context should be explicitly attached or requested; it should not silently hijack every writing interaction.

## 4. Scope and Non-Goals

### 4.1 In scope for this evolution theme

This theme should define and stage the following:

- the primary writing loop and its entry points
- the boundary between selection context, keyword cards, citations, and graph-backed context
- the role of templates after the MVP baseline
- the role of intermediate writing artifacts generated by LLM actions
- the export staging strategy after Markdown export
- the recommended split for future frontend and backend evolution work

### 4.2 Non-goals for this round

This document should not turn into a catch-all design for adjacent domains.

Not in scope:

- redesigning graph storage or graph editing architecture
- replacing the writing API with a generalized agent orchestration layer
- committing to a full `docx` or `latex` implementation in this round
- defining a universal workflow engine for all report-production tasks
- rewriting the whole modern frontend topology inside this plan

## 5. Recommended Layering

The writing workbench should evolve as five explicit layers.

### 5.1 Layer A: Core Document Loop

Responsibility:

- document open/create
- Markdown edit/preview
- save/autosave/version conflict handling
- insertion point management for generated results

Primary repo boundary:

- `WritingWorkbenchPage.tsx`
- `MarkdownEditor.tsx`
- `MarkdownPreview.tsx`
- `document_service.py`
- document endpoints in `api/writing.py`

This is the only layer that is always on.

### 5.2 Layer B: Evidence and Context Layer

Responsibility:

- selection lookup
- keyword-card retrieval
- citation basket management
- provenance preview and evidence inspection

Primary repo boundary:

- `useSelectionLookup.ts`
- `KeywordInsightSidebar.tsx`
- `WritingInsightCard.tsx`
- `CitationBasket.tsx`
- `keyword_card_service.py`
- `citation_service.py`

This layer provides evidence objects for writing. It should not decide how the final prose is generated.

### 5.3 Layer C: Graph Context Adapter

Responsibility:

- expose graph-derived context as an optional writing-side input
- map graph objects into the same context-selection contract used by evidence retrieval

Primary repo boundary:

- writing-side consumers in the workbench
- graph-facing providers from the graph domain

This layer must remain optional in the primary loop. Graph context is a structured context source, not the dominant surface of the page.

### 5.4 Layer D: Templates and Intermediate Artifacts

Responsibility:

- template starter selection
- variable interpretation and validation
- distinction between raw document body, generated snippets, reusable draft fragments, and template definitions

Primary repo boundary:

- `TemplateLibraryPanel.tsx`
- `template_service.py`
- LLM-generated result handling in the writing page

This layer should stay downstream of the core document loop. Templates help start and shape writing; they should not replace document ownership.

### 5.5 Layer E: Export and Interop

Responsibility:

- preserve Markdown as canonical source
- convert the canonical source into external delivery formats through adapters
- keep export behavior decoupled from core editing state

Primary repo boundary:

- export entrypoints in `WritingWorkbenchPage.tsx`
- `/writing/export/markdown` in `api/writing.py`

This layer should remain an adapter layer. Export needs to consume a stable document model instead of forcing the document model to mirror every output format.

## 6. Implementation Order

The recommended order is intentionally conservative because the repo already has a live workbench surface.

### Step 1: Freeze baseline and delta

Before adding more behavior, explicitly map:

- what the builtin writing workbench documents already defined
- what the current repo has already implemented
- what this evolution theme is actually adding or clarifying

Without that delta map, future changes will either duplicate the builtin plan or skip over already-shipped work.

### Step 2: Freeze the primary writing loop

The next mandatory step is to define the authoritative flow for:

- document lifecycle
- selection-driven context lookup
- citation insertion
- LLM action invocation
- write-back behavior

This step should decide what the "happy path" is before any deeper graph, template, or export evolution is expanded.

### Step 3: Freeze bounded context roles

Once the primary loop is fixed, the next job is to assign responsibilities:

- evidence cards provide supporting material
- citations represent user-accepted source references
- graph context provides structured relation hints
- templates provide starting structure
- LLM actions transform or extend text

This prevents new capability work from collapsing into one mixed assistant surface.

### Step 4: Stage templates, intermediate artifacts, and export adapters

After the context roles are clear:

- template evolution can be staged without redefining document ownership
- intermediate artifact handling can be defined without overloading LLM history
- export can be extended as an adapter concern instead of a core authoring concern

### Step 5: Refactor along stable boundaries

Only after the above decisions are frozen should future implementation work split the page and service boundaries more aggressively.

The likely candidate is to reduce orchestration pressure in `WritingWorkbenchPage.tsx` by moving stable domains into narrower modules rather than adding new feature branches directly into the page.

## 7. Serial and Parallel Relations

The execution relationship should stay simple.

### 7.1 Serial prerequisites

These items must remain serial:

1. Baseline and delta freeze
2. Primary writing loop freeze
3. Final integration and regression gate definition

Reason:

- every later choice depends on a stable definition of the main loop
- export, graph, and template decisions become noisy if the core loop is still moving

### 7.2 Parallelizable work after the core loop is frozen

Once the primary loop is frozen, the following can progress in parallel:

- evidence-context vs graph-context boundary definition
- template and intermediate-artifact staging
- export adapter staging
- LLM action contract tightening

These are parallelizable because they consume the same core loop but do not need to redefine it.

### 7.3 Cross-theme dependencies

This theme depends on adjacent themes, but only at the boundary level:

- `graph-editing-and-reporting` should define what graph-side context can be attached into writing.
- `llm-service-and-agent-platformization` should define stable action and trace behavior.
- `dual-frontend-workbench-topology` should define where the workbench sits in the broader frontend topology.

The writing-workbench theme should consume those outputs. It should not absorb the full design responsibility of those themes.

## 8. Minimal Validation

The minimum validation set should cover both structure and flow.

### 8.1 Structural validation

At least one validation pass should confirm that each stage of the primary loop maps to a concrete repo module.

Suggested structural checks:

- verify the workbench surface is still rooted in `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
- verify writing endpoints remain centralized in `main/backend/app/api/writing.py`
- verify writing contracts remain centralized in `main/backend/app/contracts/schemas/writing.py`

### 8.2 Flow validation

At least one end-to-end flow should be traceable without inventing extra systems:

1. open or create a document
2. edit Markdown
3. autosave or save
4. select text and fetch keyword cards
5. inspect a card and add a citation
6. run an LLM action on the current selection or body
7. write the result back into the document

If any of those steps require cross-domain behavior, the exact dependency should be named instead of being hidden in UI language.

### 8.3 Template and export validation

At least one validation step should prove that template and export are staged correctly:

- template validation must remain possible without converting the workbench into a template-only editor
- Markdown export must remain aligned with the canonical document body plus citation rebuild
- non-Markdown export must remain explicitly staged as a later adapter concern

### 8.4 Boundary validation

At least one validation step should confirm that graph context stays bounded:

- graph is attachable context, not a mandatory prerequisite for normal writing
- the no-graph path remains complete for the primary writing loop

## 9. Risks and Open Questions

### 9.1 Main risks

- The writing domain is already broad enough that adding graph, richer templates, and more export targets without freezing the main loop will produce another monolithic surface.
- The current workbench page already carries editor, template, citation, insight, and LLM orchestration in one place; unchecked evolution will keep increasing coupling in `WritingWorkbenchPage.tsx`.
- If graph context is not bounded early, the writing page may degrade into a graph-adjacent inspection shell instead of staying a writing surface.
- If templates are allowed to represent starter, variable system, and workflow engine simultaneously in the same phase, the product contract will become too ambiguous to implement cleanly.
- If non-Markdown export is treated as first-class before the internal document contract is frozen, export requirements will distort authoring behavior.

### 9.2 Open questions that should be resolved explicitly

- Is a keyword card sufficient as the default evidence object, or is a stronger "accepted evidence" object needed once graph context participates?
- Should selection, evidence lookup, graph attach, and LLM action share one session contract, or should graph attachment remain a separate optional context envelope?
- Should intermediate LLM outputs be stored as part of document revision flow, as reusable artifacts, or only as action history until explicitly accepted?
- How far should template variables be allowed to bind into evidence or graph context in phase 2, without turning template rendering into a hidden workflow engine?
