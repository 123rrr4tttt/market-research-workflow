# Atomic Task List: Writing Workbench Evolution (2026-03-07)

## Execution Status Snapshot

- `E1`: pending, freeze the delta between builtin design docs and the repo's already-existing writing implementation.
- `E2`: pending, freeze the primary writing loop that future work must preserve.
- `E3-E6`: pending, clarify bounded evolution topics after the core loop is fixed.
- `E7-E8`: pending, align refactor boundaries and cross-theme dependencies without reopening the core loop.
- `E9`: pending, define the minimum regression gate and close the evolution package.

## Global Serial-Parallel Rules

- `L0` serial bootstrap: `E1` must finish first because this theme is explicitly an evolution plan, not a greenfield design.
- `L1` serial core freeze: `E2` must finish before template, graph, export, or LLM evolution tasks proceed.
- `L2` parallel domain freeze:
  - context boundary: `E3`
  - template and artifact staging: `E4`
  - export staging: `E5`
  - LLM action and audit tightening: `E6`
- `L3` serial integration:
  - surface refactor boundary: `E7`
  - cross-theme alignment: `E8`
- `L4` serial closure: `E9` runs only after `E1-E8` produce a coherent package.

## Global Module Boundary Rules

- Core document loop:
  - frontend: `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - frontend components: `MarkdownEditor.tsx`, `MarkdownPreview.tsx`
  - backend: `main/backend/app/api/writing.py`, `document_service.py`
- Evidence and citation domain:
  - frontend: `useSelectionLookup.ts`, `KeywordInsightSidebar.tsx`, `WritingInsightCard.tsx`, `CitationBasket.tsx`
  - backend: `keyword_card_service.py`, `citation_service.py`
- Template and artifact domain:
  - frontend: `TemplateLibraryPanel.tsx`, generated-result handling in `WritingWorkbenchPage.tsx`
  - backend: `template_service.py`
- LLM action domain:
  - frontend: `LlmAssistantPanel.tsx`, action history/detail usage in `WritingWorkbenchPage.tsx`
  - backend: `llm_action_service.py`, LLM routes in `api/writing.py`
- Export and interop domain:
  - frontend: export trigger path in `WritingWorkbenchPage.tsx`
  - backend: `/writing/export/markdown`

No task should blur these boundaries without an explicit note explaining why the boundary is being changed.

## Global Acceptance Rules

Each task must produce the following:

- `result`: one concrete decision, contract, or implementation boundary
- `changed_modules`: the exact modules or docs it changes or constrains
- `validation`: at least one structural or flow validation step
- `risk`: one explicit follow-up risk if the task stops at its minimum scope

## Task E1: Freeze Baseline and Delta Matrix

- `目标`: Confirm what the builtin writing-workbench documents already solved, what the repo has already implemented, and what this evolution theme still needs to decide.
- `status`: pending
- `depends_on`: `[]`
- `blocks`: `["E2","E3","E4","E5","E6"]`
- `输入`:
  - `01_builtin-writing-workbench-design-2026-03-07.md`
  - `02_atomic-tasklist-builtin-writing-workbench-design-2026-03-07.md`
  - `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/contracts/schemas/writing.py`
- `输出`:
  - one baseline matrix: `designed / implemented / still-open`
  - one explicit non-goals list for evolution work
  - one repo-reality note explaining that writing page and writing API already exist
- `验收`:
  - the document no longer reads as if writing workbench were unimplemented
  - the delta list distinguishes convergence work from first-build work
  - the open items are limited to workflow, boundary, staging, and refactor decisions
- `最小验证`:
  - structurally verify the referenced page, API, and schema files exist
  - verify the delta summary does not contradict the builtin design docs
- `模块边界`:
  - allowed to change planning docs
  - not allowed to redefine adjacent themes during baseline freeze

## Task E2: Freeze the Primary Writing Loop

- `目标`: Define the authoritative user flow that all future evolution must preserve.
- `status`: pending
- `depends_on`: `["E1"]`
- `blocks`: `["E3","E4","E5","E6","E7"]`
- `输入`:
  - current workbench page behavior
  - document lifecycle endpoints
  - citation and LLM action entrypoints
- `输出`:
  - one canonical loop covering document open/create, edit, selection, context fetch, citation acceptance, action execution, and write-back
  - one happy-path sequence for no-graph usage
  - one explicit statement of what is optional versus always-on
- `验收`:
  - the flow includes save or autosave
  - the flow includes citation handling as part of normal writing, not after-the-fact cleanup
  - the flow supports both selection-level and document-level action entry
- `最小验证`:
  - trace one full path through `WritingWorkbenchPage.tsx` and `/writing` endpoints without inserting extra systems
  - confirm the same loop still works when graph context is absent
- `模块边界`:
  - may define contracts across document, citation, and LLM modules
  - may not redesign graph or export subsystems here

## Task E3: Freeze Evidence Context vs Graph Context Boundary

- `目标`: Separate evidence retrieval from graph-derived context so the workbench does not collapse into a vague assistant surface.
- `status`: pending
- `depends_on`: `["E2"]`
- `blocks`: `["E7","E8"]`
- `输入`:
  - `useSelectionLookup.ts`
  - keyword-card request and detail contracts
  - citation model
  - graph-related writing inputs already implied by source types
- `输出`:
  - one context envelope model distinguishing:
    - selection context
    - evidence card context
    - accepted citation context
    - optional graph context
  - one rule for how graph context enters writing flow
- `验收`:
  - evidence objects and graph objects do not share the same responsibility description
  - the no-graph path remains first-class
  - the accepted-citation state is distinct from raw search result state
- `最小验证`:
  - verify the context model can describe the current keyword-card and citation flows
  - verify graph is attachable without becoming mandatory for normal writing
- `模块边界`:
  - evidence/citation modules may evolve
  - graph-side systems stay external and are consumed through an adapter contract

## Task E4: Stage Templates and Intermediate Artifacts

- `目标`: Define how templates and generated artifacts evolve after the MVP baseline.
- `status`: pending
- `depends_on`: `["E2"]`
- `blocks`: `["E7","E9"]`
- `输入`:
  - `TemplateLibraryPanel.tsx`
  - `template_service.py`
  - current LLM result handling in `WritingWorkbenchPage.tsx`
- `输出`:
  - one staged model for:
    - template as starter
    - template variable validation
    - reusable generated artifacts
  - one rule for when generated content becomes document content versus standalone artifact
- `验收`:
  - templates remain subordinate to document ownership
  - intermediate artifacts are not silently merged into LLM history
  - phase 1 and phase 2 boundaries are explicit
- `最小验证`:
  - verify at least one existing template can still be applied as a normal document starter
  - verify a generated fragment can be described without assuming a full workflow-engine implementation
- `模块边界`:
  - template validation and artifact handling may evolve
  - document lifecycle remains the owner of accepted body content

## Task E5: Freeze Canonical Source and Export Staging

- `目标`: Keep Markdown as the internal canonical source and stage richer export as adapter work.
- `status`: pending
- `depends_on`: `["E2"]`
- `blocks`: `["E8","E9"]`
- `输入`:
  - export trigger in `WritingWorkbenchPage.tsx`
  - `/writing/export/markdown`
  - citation rebuild path in backend writing API
- `输出`:
  - one canonical-source statement
  - one staged export roadmap:
    - current Markdown export
    - future adapter-based exports
  - one boundary note explaining what export must not change in the authoring model
- `验收`:
  - the document does not imply `docx` or `latex` already exists
  - export is framed as downstream of document and citation reconciliation
  - canonical Markdown remains the source of truth
- `最小验证`:
  - verify the current export path is Markdown-only and citation-aware
  - verify future export requirements are stated as staged adapters, not current facts
- `模块边界`:
  - export layer may consume document and citation outputs
  - export must not redefine editor data structures

## Task E6: Tighten LLM Action and Audit Contract

- `目标`: Clarify how writing-oriented LLM actions participate in the workbench without owning the document.
- `status`: pending
- `depends_on`: `["E2"]`
- `blocks`: `["E7","E8","E9"]`
- `输入`:
  - `LlmAssistantPanel.tsx`
  - `llm_action_service.py`
  - action request and response schemas
  - action history and detail routes
- `输出`:
  - one action contract for selection-level and document-level invocation
  - one write-back rule for generated content
  - one audit note covering trace, request, and history expectations
- `验收`:
  - LLM actions are described as assistive transforms, not as page owners
  - selection-level and document-level behavior are both explicit
  - the contract keeps traceability visible
- `最小验证`:
  - verify every supported writing action can be expressed with current request schema fields
  - verify generated output, source references, and trace identifiers remain visible in the contract
- `模块边界`:
  - LLM action modules may define transformation behavior
  - document persistence still decides what becomes accepted content

## Task E7: Define the Surface Refactor Boundary

- `目标`: Decide how future work should reduce orchestration pressure in `WritingWorkbenchPage.tsx` without reopening settled product decisions.
- `status`: pending
- `depends_on`: `["E3","E4","E6"]`
- `blocks`: `["E9"]`
- `输入`:
  - current page-level state ownership
  - the outputs of `E2-E6`
  - existing writing components under `src/components/writing`
- `输出`:
  - one refactor split showing what should stay page-level versus what should move into narrower modules
  - one file-boundary rule for future work touching templates, insights, citations, and LLM panels
- `验收`:
  - the split reduces future reasons to keep adding state to the page root
  - panel behavior, citation behavior, and LLM behavior are assigned to stable module owners
  - the refactor split does not change product semantics already frozen by earlier tasks
- `最小验证`:
  - verify every major state domain in the current page has an intended owner after the split
  - verify no task requires simultaneous ownership of editor core, graph adapter, export adapter, and LLM audit logic
- `模块边界`:
  - page shell owns coordination
  - domain modules own local behavior

## Task E8: Align Cross-Theme Dependency Contracts

- `目标`: Record exactly what this theme needs from graph, LLM-platform, and frontend-topology themes, and what it does not own.
- `status`: pending
- `depends_on`: `["E3","E5","E6"]`
- `blocks`: `["E9"]`
- `输入`:
  - this evolution plan
  - adjacent CURRENT_DEV theme docs
- `输出`:
  - one dependency map with upstream expectations and local assumptions
  - one "consume, do not redesign" boundary statement for each adjacent theme
- `验收`:
  - graph dependency is limited to writing-consumable context
  - LLM-platform dependency is limited to action and trace behavior
  - frontend-topology dependency is limited to placement and integration boundaries
- `最小验证`:
  - verify the dependency notes do not absorb implementation ownership from adjacent themes
  - verify each dependency is attached to one specific boundary, not to a vague collaboration statement
- `模块边界`:
  - this task changes planning boundaries only
  - no adjacent theme should be rewritten from here

## Task E9: Define the Minimum Regression Gate and Closure Pack

- `目标`: Close the evolution package with a small but defensible validation set for future implementation.
- `status`: pending
- `depends_on`: `["E4","E5","E7","E8"]`
- `blocks`: `[]`
- `输入`:
  - frozen outputs from `E1-E8`
  - current structural entrypoints in frontend and backend writing modules
- `输出`:
  - one structural validation set
  - one flow validation set
  - one staged-risk summary for deferred work
- `验收`:
  - the validation set covers at least:
    - document lifecycle
    - selection to evidence to citation flow
    - LLM action invocation and write-back
    - template validation
    - Markdown export
  - deferred items such as non-Markdown export are explicitly listed as deferred
- `最小验证`:
  - structural:
    - verify writing entrypoints still exist in the page, API, and schema modules
  - flow:
    - verify one no-graph path and one graph-attached path are both described
  - staging:
    - verify deferred export targets are not presented as already implemented
- `模块边界`:
  - validation pack spans frontend, backend, and planning docs
  - closure must not reopen the scope freeze from `E1-E2`
