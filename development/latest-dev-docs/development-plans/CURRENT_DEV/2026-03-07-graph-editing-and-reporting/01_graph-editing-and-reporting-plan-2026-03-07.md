# Graph Editing and Reporting Plan (2026-03-07)

> 日期：2026-03-07
> 范围：graph editing, sync semantics, audit/version minimums, and graph-to-writing/reporting handoff
> 状态：theme plan, used to freeze requirement shape and execution order before implementation

## 2026-05-22 Closure Refresh

Status: `未封口 / 后端合同已部分落地，前端 graph page 集成仍是 blocker`.

Current evidence changes the baseline:

- Backend workflow graph edit-contract code exists in `main/backend/app/services/workflow_graph/edit_contract.py`.
- Backend curated graph lifecycle exists in `main/backend/app/services/workflow_graph/curated_service.py`, including draft save, submit, sync, rollback, audit listing, evidence pack, and writing/reporting handoff construction.
- API endpoints exist in `main/backend/app/api/workflow_graph.py` for `/curated/{graph_id}/draft`, `/submit`, `/sync`, `/rollback`, `/audit`, `/evidence-pack`, and `/handoff/{reporting|writing}`.
- Writing/reporting consumers have graph-context adapters through `main/backend/app/contracts/schemas/writing.py` and `main/backend/app/services/writing/keyword_card_service.py`.
- Tests exist for curated service, workflow graph API handoffs, handoff store replay, and writing keyword-card graph context.

The remaining blocker is the boundary between the existing frontend graph page and these backend contracts. `main/frontend-modern/src/pages/GraphPage.tsx` still imports graph read/config/structured-search APIs only; no current frontend evidence shows that its local draft UI submits to the curated workflow-graph endpoints or consumes their conflict/audit/handoff responses.

Status by original layer:

- Layer A editable object boundary: `partial`. Backend distinguishes `template_graph`, `generated_graph_snapshot`, and `curated_business_graph`; frontend GraphPage still mixes visual graph editing and template/version controls without a documented curated-submit bridge.
- Layer B draft/sync contract: `partial`. Backend revision/conflict semantics exist; frontend GraphPage has local draft state but no verified curated submit flow.
- Layer C audit/rollback/version semantics: `partial`. Backend supports revision, audit, rollback, and separate curated graph versions; frontend integration evidence is missing.
- Layer D graph evidence handoff: `partial`. Backend evidence pack and writing/reporting handoffs exist; frontend entry/owner is not wired or documented as closed.

Closure blockers:

1. Decide whether GraphPage owns the curated graph bridge or whether a separate workflow-graph screen/API client owns it.
2. Add or verify frontend API wrappers for the curated endpoints if GraphPage is the owner.
3. Prove one branch-local flow: local graph edit -> backend curated draft/save or submit -> conflict/success response -> evidence pack -> writing or reporting handoff.
4. Keep template/version actions separate from curated business graph governance unless a mapping is explicitly implemented and tested.

Minimal validation steps for closure:

```bash
cd /Users/wangyiliang/market-research-workflow.worktrees/graph-plan-refresh

rg -n "GRAPH_OBJECT_KINDS|curated_business_graph|temporary node_id|system-managed" main/backend/app/services/workflow_graph/edit_contract.py
rg -n "save_draft|submit_draft|sync_graph|rollback|build_evidence_pack|build_writing_handoff|build_reporting_handoff" main/backend/app/services/workflow_graph/curated_service.py
rg -n "curated/.*/draft|curated/.*/submit|evidence-pack|handoff/writing|handoff/reporting" main/backend/app/api/workflow_graph.py
rg -n "curated|evidence-pack|handoff|workflow-graph/curated" main/frontend-modern/src/lib main/frontend-modern/src/pages/GraphPage.tsx

cd main/backend
.venv311/bin/python -m pytest -q tests/unit/test_workflow_graph_curated_service_unittest.py tests/unit/test_workflow_graph_handoff_store_unittest.py tests/unit/test_writing_keyword_card_service_unittest.py tests/integration/test_workflow_graph_api_unittest.py

cd ../frontend-modern
npm run test:e2e -- tests/e2e/graphpage.spec.ts
```

Worker lane 5 validation result:

- Passed backend graph/workflow/writing validation from this worktree's `main/backend` directory: `51 passed` for graph projection/exporter/persistence, admin graph standardization, curated workflow graph service, handoff store, writing keyword-card graph context, and workflow graph API tests.
- Passed negative frontend ownership smoke: `rg -n "curated|evidence-pack|handoff|workflow-graph/curated" main/frontend-modern/src/lib main/frontend-modern/src/pages/GraphPage.tsx` returned no matches, confirming the documented frontend bridge blocker.
- Passed frontend GraphPage e2e in `codex/devdocs-graph-frontend-e2e`: `npm --prefix main/frontend-modern run test:e2e -- tests/e2e/graphpage.spec.ts` returned `3 passed`. The new e2e verifies either a real `react-force-graph-3d` canvas with data-backed scene node objects or, on this headless WebGL-limited runner, visible automatic fallback to `legacy-projection` without blanking the page.
- Passed formatting gate: `git diff --check`.

Closure decision: do not archive. This topic is no longer accurately described as fully pending, but the user-facing GraphPage-to-curated-contract bridge is not proven.

## 1. Goal

This theme should turn graph work from a mostly visual/template-oriented editor into a controlled business workflow that can be:

1. edited as a structured object;
2. synchronized with explicit success and failure semantics;
3. audited and versioned at a minimum governance level;
4. consumed by writing/reporting through a stable intermediate payload.

This plan does not attempt to design a full collaborative knowledge graph platform in one pass. The immediate objective is to freeze the minimum contract that later implementation work can follow without mixing template editing, generated graph review, and curated business graph maintenance.

## 2. Current Baseline

### 2.1 Frontend baseline

Verified frontend anchors already exist:

- `main/frontend-modern/src/pages/GraphPage.tsx`
- `main/frontend-modern/src/pages/graph/hooks/useGraphDraft.ts`

Verified current behavior exposed by those files:

- `GraphPage.tsx` contains `editMode` and `graphEditStatus`.
- `GraphPage.tsx` includes draft editing controls for node and edge creation, field editing, and deletion.
- `GraphPage.tsx` also includes template/version actions such as create, rename, delete, save version, load version, and activate version.
- `useGraphDraft.ts` already exposes local draft operations:
  - `createNode`
  - `updateNodeByKey`
  - `removeNodesByKeys`
  - `createEdgeByNodeKeys`
  - `removeEdgeAt`
  - `resetDraft`
  - `markSaved`

Baseline conclusion:

- the frontend is not starting from zero;
- the current editing layer is real, but it still reads closer to a graph/template draft editor than a frozen business graph contract;
- the contract between local draft state and backend persistence is still the main gap.

### 2.2 Backend baseline

Verified backend graph anchors already exist:

- graph build/projection/doc typing:
  - `main/backend/app/services/graph/builder.py`
  - `main/backend/app/services/graph/projection.py`
  - `main/backend/app/services/graph/doc_types.py`
- graph export and mapping:
  - `main/backend/app/services/graph/exporter.py`
  - `main/backend/app/services/graph/mapping.py`
- graph persistence:
  - `main/backend/app/services/graph/persistence/graph_node_reader.py`
  - `main/backend/app/services/graph/persistence/graph_node_writer.py`
  - `main/backend/app/services/graph/persistence/graph_node_alias_resolver.py`
- currently visible API anchors:
  - `main/backend/app/api/admin.py`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/api/llm_report.py`

Baseline conclusion:

- graph read, projection, export, and persistence primitives already exist;
- the repository already has routes that touch graph-adjacent and writing/reporting workflows;
- what is still not frozen in the docs is the user-facing edit contract: editable object class, error vocabulary, conflict handling, and the handoff payload for downstream consumers.

### 2.3 Writing/reporting consumption baseline

Verified cross-domain anchors already exist:

- `main/backend/app/contracts/schemas/writing.py`
- `main/backend/app/services/writing/keyword_card_service.py`
- `main/backend/app/api/llm_report.py`
- `main/backend/app/services/llm_report_generator.py`
- `main/backend/app/services/llm_report_source_enrichment.py`

Verified reusable signals:

- writing schemas already allow `source_type = "graph"`;
- `keyword_card_service.py` already contains graph-aware source typing logic;
- reporting services already provide a place where graph-derived evidence can be enriched or transformed before final report generation.

Baseline conclusion:

- graph output is already recognized as a source category;
- the missing piece is not "can graph appear anywhere downstream" but "what exact payload shape should a curated graph hand over to downstream consumers."

## 3. Requirement Clarifications

### 3.1 Primary scenarios assumed by this plan

This plan assumes three first-order scenarios and keeps them separate:

1. an operator or analyst reviews and edits graph nodes/edges in the graph UI;
2. the edited graph state is synchronized with backend validation and conflict feedback;
3. a selected graph result is transformed into a writing/reporting input rather than being passed to LLM consumers as raw UI state.

### 3.2 Problems this iteration must solve

This theme is only useful if it answers the following practical questions:

- What graph object is actually editable in this iteration?
- Which node and edge fields are user-editable versus derived/system-managed?
- What happens when draft submit succeeds, fails validation, or hits a version conflict?
- What minimum audit trail is required before graph edits become trusted inputs?
- What exact intermediate payload is allowed to cross into writing/reporting?

### 3.3 Explicit clarifications to freeze

The following points must be written down before code-level implementation is treated as stable:

- object boundary:
  - template graph
  - generated graph snapshot
  - curated business graph
- edit boundary:
  - allowed node fields
  - allowed edge fields
  - delete semantics for nodes and connected edges
- sync boundary:
  - draft lifecycle
  - submit response semantics
  - minimum conflict token or revision semantics
- consumption boundary:
  - graph evidence pack or equivalent intermediate object
  - first consumer path into writing or reporting

## 4. Scope and Non-Goals

### 4.1 In scope

- define the minimum business contract for node and edge create/update/delete;
- define draft, submit, sync, failure, and conflict semantics;
- define the minimum audit, rollback, and version vocabulary;
- define the graph evidence pack, or an equivalent stable handoff payload;
- define one first consumer path from graph output into writing/reporting;
- keep boundaries explicit versus adjacent themes such as typed knowledge organization and writing workbench evolution.

### 4.2 Non-goals

- redesign the graph rendering engine, layout engine, or 2D/3D renderer stack;
- define the full knowledge type system in this theme;
- rebuild the full writing workbench in this theme;
- introduce multi-user real-time collaboration as phase 1 scope;
- equate workflow graph DSL or template management with curated business graph governance;
- assume that current template/version actions are already sufficient as business audit/version semantics.

## 5. Recommended Layering

### 5.1 Layer A: Editable graph object boundary

The first layer should freeze which object class is being edited.

Recommended separation:

- template graph:
  reusable shape or seeded structure;
- generated graph snapshot:
  machine-produced graph result pending review;
- curated business graph:
  the graph state allowed to become a durable reporting/writing source.

Reason:

- without this split, permissions, versioning, conflict handling, and downstream trust will collapse into one ambiguous workflow.

### 5.2 Layer B: Draft and sync contract

The second layer should connect the existing frontend draft model to backend persistence semantics.

The minimum contract should clarify:

- node create/update/delete payload shape;
- edge create/update/delete payload shape;
- temporary client identifiers versus durable backend identifiers;
- what `submit` returns on success;
- what validation failure returns;
- what conflict failure returns;
- whether the client must reload, merge, or explicitly overwrite on conflict.

### 5.3 Layer C: Audit, rollback, and version semantics

The third layer should turn graph editing from "editable" into "governed."

The minimum governance model should answer:

- who changed what;
- when the change happened;
- which project/context the change belongs to;
- whether rollback happens by whole submit, by object set, or by snapshot restore;
- whether current template/version actions are reused, mapped, or kept separate from business graph version semantics.

### 5.4 Layer D: Graph evidence handoff

The fourth layer should define the only approved payload that writing/reporting may consume.

The handoff should not be raw frontend graph objects. It should be a narrower evidence-oriented object that can at least express:

- selected nodes or node summaries;
- selected relations or relation chains;
- provenance or traceable identifiers;
- optional subgraph summary text suitable for downstream generation;
- enough metadata for writing/reporting to treat graph content as auditable evidence instead of ad hoc prompt text.

## 6. Implementation Order

### 6.1 Step 1: Freeze object boundary and baseline delta

Required output:

- one clear distinction among template graph, generated graph snapshot, and curated business graph;
- one baseline delta list that says what already exists versus what remains undefined.

This step is serial and must happen first because every later decision depends on what object is being edited.

### 6.2 Step 2: Freeze the minimum edit contract

Required output:

- node and edge input/output contract;
- local draft lifecycle;
- submit response semantics;
- error vocabulary for validation failure, object missing, and version conflict.

This step should convert the existing draft UI into a business-facing contract rather than a loose editing surface.

### 6.3 Step 3: Add minimum governance semantics

Required output:

- minimum audit model;
- minimum rollback strategy;
- minimum version or revision semantics.

This step should remain narrow. It is about controlled governance, not enterprise workflow expansion.

### 6.4 Step 4: Freeze graph evidence pack and first consumer

Required output:

- one stable intermediate payload definition;
- one first graph-to-writing or graph-to-report path;
- clear rule that downstream consumers read evidence pack data instead of raw draft payloads.

### 6.5 Step 5: Only then optimize graph tasks and broader reporting linkage

Required output:

- follow-up optimization plan for generated graph review, structured graph tasks, or broader reporting reuse;
- explicit statement of what remains phase 2.

## 7. Parallel vs Serial Relationships

### 7.1 Serial dependencies

- serial-1:
  object boundary freeze must happen before edit contract freeze;
- serial-2:
  edit contract freeze must happen before governance and consumer work are treated as stable;
- serial-3:
  graph evidence consumer integration should wait until the evidence pack is frozen.

### 7.2 Safe parallel slices after the contract is frozen

After the minimum edit contract is frozen, two workstreams can proceed in parallel:

- governance track:
  audit, rollback, and version semantics;
- consumer track:
  evidence pack definition and first writing/reporting handoff path.

They should merge again before any broader phase-2 optimization is planned.

### 7.3 Cross-theme boundaries that must remain serial by ownership

- `typed-knowledge-organization` owns the meaning and hierarchy of knowledge objects;
- this theme owns how graph-shaped objects are edited, synchronized, and handed off;
- `writing-workbench-evolution` owns the writing UI and authoring flow;
- this theme only defines how graph evidence becomes a valid writing/reporting input;
- `llm-service-and-agent-platformization` owns provider/orchestration concerns, not graph evidence semantics.

## 8. Minimum Validation

The minimum validation for this theme should cover one structural check and one flow check before implementation proceeds.

### 8.1 Structural validation

Confirm that the documented anchors still exist and still justify the baseline:

```bash
rg -n "editMode|graphEditStatus|saveVersion|activateVersion" main/frontend-modern/src/pages/GraphPage.tsx
rg -n "createNode|updateNodeByKey|removeNodesByKeys|createEdgeByNodeKeys|resetDraft|markSaved" main/frontend-modern/src/pages/graph/hooks/useGraphDraft.ts
rg -n "source_type: Literal\\[\"document\", \"resource\", \"graph\"\\]" main/backend/app/contracts/schemas/writing.py
```

Expected result:

- the graph UI still exposes local editing state and template/version operations;
- the draft hook still exposes the local editing primitives;
- writing schema still treats graph as an allowed source type.

### 8.2 Flow validation

Confirm that one minimum end-to-end path can be described without inventing missing layers:

1. select or edit graph objects in `GraphPage.tsx`;
2. map draft state to a backend-safe submit contract;
3. classify the response as success, validation failure, or conflict;
4. transform accepted graph output into a graph evidence pack;
5. hand that pack to writing/reporting consumers through existing writing/report anchors.

Expected result:

- the flow can be described without treating raw UI draft objects as the final downstream payload;
- the flow explicitly names where conflict handling and evidence shaping happen.

### 8.3 Boundary validation

Before implementation starts, the owner should be able to answer all three questions in one page:

- what is editable;
- what is synchronizable;
- what is consumable by writing/reporting.

If any of the three is still ambiguous, the implementation plan is not ready.
