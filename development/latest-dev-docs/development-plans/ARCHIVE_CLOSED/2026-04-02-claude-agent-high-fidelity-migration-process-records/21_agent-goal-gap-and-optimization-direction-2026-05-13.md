# Agent Goal Gap And Optimization Direction

Date: 2026-05-13
Status: superseded by 2026-05-14 closure audit for current implementation state
Mainline: Claude Code level AgentCore reconstruction

2026-05-14 update: the priority queue and acceptance matrix in this document have been reconciled in [`41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`](./41_agent-high-fidelity-migration-closure-audit-2026-05-14.md). Treat this file as the gap model that drove implementation, not as the latest open-gap source.

2026-05-14 matrix update: 41 also introduces R3, a new standing requirement that Agent system-capability use for research, source discovery, material supplementation, verification, and comparison must run as a matrix rather than as one serial tool lane. Therefore the optimization directions below should be read with an extra constraint: internal context, keyword variants, provider/tool routes, evidence classes, and verification gates must be branched, merged, and ranked before a final answer or ingest step.

## Purpose

This document records the current distance between the implemented agent system and the original goal:

> a highly interactive intelligent project agent that can talk freely, understand project materials and data, choose tools by model reasoning, search internal and external evidence when needed, split long tasks, and collaborate with the writing workbench.

This is a product-and-architecture gap document. It must not be used as a closure claim. Previous checklist rows in older runtime documents remain historical implementation evidence, not proof that the final user-facing goal is complete.

## Current Completion Assessment

Current completion is best treated as mid-stage: the core surfaces exist, but the end-to-end behavior is not yet consistently Claude Code level.

Estimated state:

- AgentCore and tool surface: roughly 70 percent mature for covered backend paths.
- Free chat and simple project read flows: roughly 65 percent mature, with remaining risk around routing drift and answer quality.
- Project material/data understanding: roughly 50 percent mature, because source-library, stored project data, artifacts, graph data, and writing documents are not yet consistently unified in one model context.
- Writing workbench integration: roughly 40 to 50 percent mature, because document tools and writeback exist, but full canvas-aware editing, selection context, citation insertion, and replacement flows are still incomplete.
- Long investigation and writing workflows: roughly 45 to 55 percent mature, because planning, artifacts, trace tools, and source discovery exist, but durable multi-stage execution is not yet a reliable product flow.
- Frontend interaction maturity: roughly 50 to 60 percent mature, because streaming and tool panels exist, but thinking hangs, session/page decoupling, compact chat scrolling, and workbench cross-navigation still require hardening.

The main risk is not the absence of components. The risk is that the components still behave like adjacent capabilities rather than a single model-led agent loop.

## Gap Model

The remaining gap should be tracked through six dimensions.

| Dimension | Current State | Target State | Gap |
| --- | --- | --- | --- |
| Model ownership | Turn decision and tool windows exist, but rule hints still shape too much behavior. | Model receives a compact project/tool context and owns direct answer, tool choice, follow-up tool calls, and final synthesis. | Reduce rule semantics to guardrails, budgets, permission, and tool-window pruning. |
| Material semantics | Project materials, stored data, source-library items, external sources, artifacts, and writing documents are partially separated. | Agent understands material category before acting: internal/existing, internal/generated, source-library/data-source, external/discovery, external/ingest. | Add one shared material ontology used by router hints, tool descriptions, project context bundle, and final answer synthesis. |
| Tool loop | Tools are registered and many are executable, but many flows still look like one-shot selected capability calls. | Claude Code style loop: model calls tools, observes results, decides next tool or final answer, and can repair parameters. | Strengthen AgentCore query loop around repeated tool_result feedback and model-owned continuation. |
| Project context | Read tools return data, but synthesis across project summary, structured data, graph, artifacts, source-library state, and writing documents is uneven. | A single project context bundle can answer "what do we already have" and "what is missing" without confusing source-library with project materials. | Build a project context aggregator with compact evidence ranking and provenance labels. |
| Writing collaboration | Document list/read/create/paragraph insert and diff review exist. | Workbench supports selection-aware context, cursor/range edits, insert/replace/rewrite, citation insertion, preview, accept/reject, and versioned rollback. | Add canvas-aware write tools and replace legacy writing AI flows with AgentCore calls. |
| Long work | Task plan, resume bundle, investigation trace, and source planning exist. | Long writing/investigation tasks can split, search internal data, identify gaps, search external sources, persist leads, write artifacts, and resume across page switches. | Add durable run state, stage transitions, gap detection, source intake, and user-visible progress. |

## Material Ontology Requirement

The agent must stop treating every "资料" request as "来源库". It also must not make "项目资料" mean only stored structured rows.

Use these categories:

- `internal_existing`: project-local materials that already exist, including structured data, documents, graph nodes, writing documents, reports, artifacts, and prior session outputs.
- `internal_generated`: materials produced by the agent in this project, including drafts, summaries, investigation traces, source plans, tables, and generated reports.
- `source_catalog`: source-library or data-source entries that describe where/how collection can run.
- `external_discovery`: external/web/source discovery that plans candidate searches, URLs, institutions, databases, or query directions without ingesting yet.
- `external_ingest`: actual external fetch/collection/ingest/writeback, governed by trust gates, budget, project isolation, and hard-deny rules.

Routing intent should use abstract dimensions, not long phrase lists:

- scope: `internal` / `external` / `mixed` / `unknown`
- material state: `existing` / `generated` / `catalog` / `to_collect`
- work context: `conversation` / `project_read` / `writing` / `investigation` / `execution`
- risk: `read_only` / `write_shared` / `write_external` / `privileged`

Expected behavior:

- "已有资料", "项目库里的资料", "本地材料" -> prefer `internal_existing`.
- "来源库", "数据源", "采集入口", `item_key` -> prefer `source_catalog`.
- "外部资料", "网上资料", "全网", "新来源" -> prefer `external_discovery`, then `external_ingest` only when execution is explicit and governed.
- "帮我补充资料" outside a writing context -> treat as a collection/supplementation goal: inspect internal context first, then plan governed discovery/collection.
- "写作时帮我补充资料" -> prefer internal project materials first; ask or branch to external only if the user requests external material or internal coverage is insufficient.
- "写作时帮我补充外部资料" -> combine current writing context with `external_discovery` and governed collection.

## Optimization Direction

### O1: Shared Material Ontology

Create a shared material classifier/output contract that is consumed by:

- turn decision hints;
- tool-window selection;
- project context builder;
- model prompt protocol;
- frontend tool labels;
- final answer synthesis.

This contract must be short, inspectable, and testable. It should not hardcode user sentences as behavior.

### O2: Project Context Bundle

Add a read-only bundle builder that can answer:

- What project materials already exist?
- Which structured datasets are relevant?
- Which graph nodes or relations are relevant?
- Which artifacts or prior outputs are relevant?
- Which writing documents are active?
- Which source-library entries are only collection entrypoints?
- What evidence is missing?

The model should receive this bundle before deciding whether to search externally.

### O3: Model-Owned Tool Loop

Move from static selected capabilities to repeated model tool feedback:

1. model sees compact context and available tool schemas;
2. model builds a query/capability matrix for broad evidence tasks, including internal context, keyword variants, source/tool routes, and verification gates;
3. model calls one or more read-only tools in branches where the task needs breadth;
4. tool results are compacted, deduplicated, ranked, and fed back;
5. model chooses final answer, another matrix branch, or governed execution;
6. final answer names concrete data, documents, artifacts, sources, and next inspectable state.

Rules may veto or constrain execution but should not be the normal semantic router.

### O4: Writing Workbench Agent Contract

Replace the original writing AI module with AgentCore-backed tools:

- read active document and selection;
- include selected text, cursor, block id, and surrounding paragraphs in context;
- search internal materials and artifacts for evidence;
- optionally plan external source discovery;
- propose insert/replace/rewrite as a diff;
- write only through versioned tools;
- return provenance and citations;
- allow locate, accept, reject, and rollback.

### O5: Long Task Runtime

Long investigation and long writing must have durable state:

- plan stages;
- internal evidence pass;
- gap list;
- external discovery plan;
- source intake and trust gates;
- clue trace;
- draft/artifact outputs;
- resumable next actions;
- cancellation and retry state.

The frontend should subscribe to task state rather than block on a page-level request.

### O6: Frontend Interaction Maturity

AgentChat and the writing workbench should converge toward this interaction model:

- stream visible progress within one second;
- keep chat content in a bounded scroll container;
- preserve session and running task state across page switches;
- fold tool details by default;
- show material category labels: internal existing, generated artifact, source catalog, external discovery, external ingest;
- show writing edits as diffs next to the document, not only as chat text.

## Priority Queue

P0:

1. Implement shared material ontology and apply it to turn decision, tool window, project context bundle, and tests.
2. Make "project materials" and "source catalog" visibly distinct in tool summaries and final answers.
3. Add scenario tests for:
   - "项目库里已有资料有哪些"
   - "帮我补充资料"
   - "写作时帮我补充资料"
   - "写作时帮我补充外部资料"
   - "当前有哪些来源库 item"

P1:

1. Build project context bundle across summary, structured data, graph, artifacts, writing documents, and source-library state.
2. Feed the bundle to the model before external discovery.
3. Add contentfulness gates requiring answers to name concrete internal materials or explain the absence.

P2:

1. Add writing selection/cursor/range tools.
2. Route writing AI actions through AgentCore instead of legacy isolated writing prompts.
3. Add end-to-end tests for selection -> internal evidence -> diff proposal -> versioned writeback.

P3:

1. Convert long investigation and long writing flows into durable stage machines.
2. Add traceable external discovery and source intake states.
3. Verify page switch and hard refresh recovery.

## Acceptance Matrix

| Scenario | Expected Result | Closure Gate |
| --- | --- | --- |
| Normal fact question | Natural answer, no project execution. | SSE final answer visible; no `agent_batch`; no tool chips unless useful. |
| Project material inventory | Reads internal project context and distinguishes documents, data, graph, artifacts, writing docs. | Final answer names concrete categories and counts. |
| Source-library question | Reads source catalog only; does not imply those are existing project materials. | Final answer labels them as collection/data-source entries. |
| General supplement request | Inspects internal context, then prepares discovery/collection plan if needed. | Tool trace shows internal-first then discovery/collection boundary. |
| Writing supplement request | Reads active writing context and internal project materials first. | Draft response cites internal materials or states missing coverage before external search. |
| Writing external supplement | Combines writing context with external discovery and governed collection. | External action is explicit, bounded, and recoverable. |
| Research/source matrix request | Builds query variants and capability/provider branches before conclusion. | Trace or artifact shows keyword matrix, tool/provider matrix, evidence ranking, and unresolved gaps. |
| Long investigation | Splits stages, stores leads, traces clues, persists artifacts. | Refresh/reopen can resume the same task and show progress. |
| Workbench edit | Uses selection/range, proposes diff, writes through version lock. | User can locate, accept/reject, and inspect provenance. |

## Closure Rule

Do not mark the Claude Code level agent goal complete until:

- the material ontology is implemented across backend routing, tool windows, final answer synthesis, and frontend labels;
- project context bundle can unify internal materials without confusing them with source-library entries;
- writing workbench actions are AgentCore-backed and selection-aware;
- long task flows survive page switch/hard refresh;
- research/source/material workflows demonstrate matrix capability invocation rather than single serial search;
- scenario matrix above passes from the browser, not only unit tests.
