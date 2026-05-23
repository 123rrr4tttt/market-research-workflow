# Atomic Task List: Graph Editing and Reporting (2026-03-07)

## Execution Status Snapshot

- 2026-05-22 Wave6 status: `未封口 / GraphPage draft-submit-reporting handoff bridge proven; audit/rollback/writing UI open`.
- `A1`: partial / needs update. Backend code now names `template_graph`, `generated_graph_snapshot`, and `curated_business_graph`; GraphPage owns a narrow curated bridge, but full data-source migration is out of scope.
- `A2`: partial / needs update. Backend edit-contract validation exists for nodes/edges, system-managed fields, temporary IDs, duplicates, and missing endpoints; GraphPage draft-to-contract mapping is proven by the focused e2e.
- `A3`: partial / needs update. Backend submit/sync conflict semantics exist through revision checks; GraphPage draft save/submit/sync exists, but conflict UX is still generic.
- `A4`: partial. Backend audit, rollback, and curated revision semantics exist; frontend/template-version mapping remains explicitly open.
- `A5`: partial / needs update. Backend graph evidence pack route is proven through API-level round-trip evidence; GraphPage reporting handoff now calls the backend evidence-pack-backed handoff route instead of passing raw UI objects downstream.
- `A6`: partial / reporting path proven. Backend reporting/writing handoff routes persist, list, and replay through the workflow graph run store; GraphPage now triggers reporting handoff, while writing handoff remains backend/API-client only.
- `A7`: pending. Closure requires audit/rollback UX decision, writing handoff owner decision, clue-chain mapping decision, and branch-local structural/e2e checks.

## Global Serial-Parallel Rules

- `L0` serial bootstrap:
  - `A1` must complete first.
- `L1` serial core:
  - `A2 -> A3`
- `L2` parallel expansion:
  - governance track: `A4`
  - consumer track: `A5`
- `L3` serial merge:
  - `A6` depends on both `A3` and `A5`
- `L4` serial closure:
  - `A7` runs after `A1-A6`

## Global Module Boundary Rules

- graph UI boundary:
  - owns draft state, editing affordances, and local user feedback;
  - does not define downstream report payloads.
- graph sync boundary:
  - owns backend-safe edit requests, validation responses, conflict responses, and revision semantics;
  - does not redefine knowledge taxonomy.
- graph governance boundary:
  - owns audit, rollback, and version vocabulary for curated graph edits;
  - does not replace template management with assumed business governance unless explicitly mapped.
- writing/reporting boundary:
  - consumes graph evidence packs or equivalent stable payloads;
  - must not consume raw frontend draft objects as the canonical interface.

## Global Minimum Validation Rules

Each task should leave behind:

- one structural verification:
  - file anchor, symbol search, or contract check;
- one flow verification:
  - a short step list proving where the task connects to the next boundary.

## Task A1: Freeze Baseline and Editable Object Boundary

- Goal: Confirm what the repository already supports and freeze which graph object class is editable in this theme.
- status: partial / needs update, backend object kinds exist; GraphPage owns narrow curated bridge
- depends_on: `[]`
- blocks: `["A2","A7"]`
- Input:
  - `01_graph-editing-and-reporting-plan-2026-03-07.md`
  - `main/frontend-modern/src/pages/GraphPage.tsx`
  - `main/frontend-modern/src/pages/graph/hooks/useGraphDraft.ts`
  - `main/backend/app/services/graph/persistence/*`
- Output:
  - one baseline delta summary
  - one editable-object boundary note covering template graph, generated graph snapshot, and curated business graph
- Acceptance:
  - existing draft editing ability is clearly separated from still-missing business contract semantics
  - template/version behavior is not silently treated as business governance
- Module boundary:
  - documentation only, no new runtime behavior
- Minimum verification:
  - `rg -n "editMode|graphEditStatus|saveVersion|activateVersion" main/frontend-modern/src/pages/GraphPage.tsx`
  - `rg -n "createNode|updateNodeByKey|removeNodesByKeys|createEdgeByNodeKeys|resetDraft|markSaved" main/frontend-modern/src/pages/graph/hooks/useGraphDraft.ts`

## Task A2: Define the Minimum Node and Edge Edit Contract

- Goal: Freeze the minimum create/update/delete contract for nodes and edges.
- status: partial / needs update, backend validation exists; frontend draft-to-contract mapping proven by GraphPage e2e
- depends_on: `["A1"]`
- blocks: `["A3","A4","A5"]`
- Input:
  - frozen editable-object boundary from `A1`
  - frontend draft operations already exposed by `useGraphDraft.ts`
  - backend graph persistence anchors under `main/backend/app/services/graph/persistence/`
- Output:
  - one node contract note
  - one edge contract note
  - one rule set for temporary client ids versus durable backend ids
- Acceptance:
  - user-editable fields are separated from derived/system-managed fields
  - delete semantics for node-connected edges are explicit
  - duplicate edge and missing-node cases are called out
- Module boundary:
  - graph edit contract only; no audit or reporting payload design here
- Minimum verification:
  - structural:
    - compare draft operations with proposed contract fields
  - flow:
    - describe one `create node -> create edge -> delete node` path and resulting backend expectations

## Task A3: Define Draft, Submit, Sync, and Error Semantics

- Goal: Turn the existing draft editor into a controlled submit contract with explicit feedback categories.
- status: partial / needs update, backend revision/conflict semantics exist; GraphPage submit path verified, conflict UX generic
- depends_on: `["A2"]`
- blocks: `["A4","A6"]`
- Input:
  - edit contract from `A2`
  - current frontend draft lifecycle in `useGraphDraft.ts`
  - current API anchors in `main/backend/app/api/admin.py`
- Output:
  - one draft lifecycle note
  - one submit response vocabulary covering success, validation failure, object missing, and version conflict
  - one recommendation on revision or version token handling
- Acceptance:
  - the doc no longer treats "submit failed" as a generic toast-level outcome
  - conflict behavior is explicit about reload, merge, or overwrite expectations
  - success responses are distinct from save-local-only state changes
- Module boundary:
  - sync semantics only; downstream evidence shaping stays out of scope
- Minimum verification:
  - structural:
    - confirm `admin.py` remains the current graph-adjacent API anchor
  - flow:
    - write one `edit -> submit -> success` path and one `edit -> submit -> conflict` path

## Task A4: Define Minimum Audit, Rollback, and Version Semantics

- Goal: Add the minimum governance layer required for trusted graph edits.
- status: partial, backend audit/rollback exists; template-version mapping still open
- depends_on: `["A3"]`
- blocks: `["A7"]`
- Input:
  - sync/error contract from `A3`
  - graph persistence anchors
  - current template/version behavior in `GraphPage.tsx`
- Output:
  - one audit field list
  - one rollback scope decision
  - one version-semantics note describing whether template versions and curated graph versions are separate or mapped
- Acceptance:
  - audit covers actor, object scope, timestamp, and project/context minimums
  - rollback scope is explicit
  - template version operations are not assumed to equal curated graph governance without written mapping
- Module boundary:
  - governance only; no writing/reporting payload design here
- Minimum verification:
  - structural:
    - review template/version anchors in `GraphPage.tsx`
  - flow:
    - describe one `submit -> audit record -> rollback target` path

## Task A5: Define the Graph Evidence Pack

- Goal: Define the only approved graph-shaped payload that writing/reporting may consume.
- status: partial / needs update, API evidence pack route proven; GraphPage reporting handoff uses backend pack route
- depends_on: `["A2"]`
- blocks: `["A6","A7"]`
- Input:
  - edit contract from `A2`
  - writing/reporting anchors:
    - `main/backend/app/contracts/schemas/writing.py`
    - `main/backend/app/services/writing/keyword_card_service.py`
    - `main/backend/app/api/llm_report.py`
    - `main/backend/app/services/llm_report_source_enrichment.py`
- Output:
  - one graph evidence pack definition
  - one allowed field list for downstream consumption
  - one rule stating what raw graph UI fields must not cross the boundary
- Acceptance:
  - writing/reporting consumers receive evidence-oriented payloads, not raw draft objects
  - the payload can represent selected nodes, relations, and provenance at a minimum
  - the pack is narrow enough to stay stable when UI editing details change
- Module boundary:
  - consumer-facing payload only; no audit/version semantics here
- Minimum verification:
  - `rg -n "source_type: Literal\\[\"document\", \"resource\", \"graph\"\\]" main/backend/app/contracts/schemas/writing.py`
  - `rg -n "source_type=.*graph|source_type == \\\"graph\\\"" main/backend/app/services/writing/keyword_card_service.py`
  - Wave3 F route evidence: [graph-handoff-evidence/2026-05-22](../../../automation-runs/graph-handoff-evidence/2026-05-22/README.md)

## Task A6: Define the First Graph-to-Writing/Reporting Handoff Path

- Goal: Document one minimum flow from edited graph output to a downstream writing/report consumer.
- status: partial / reporting path proven, backend handoff route/persistence/replay proven; GraphPage reporting owner exists, writing owner open
- depends_on: `["A3","A5"]`
- blocks: `["A7"]`
- Input:
  - sync/error contract from `A3`
  - graph evidence pack from `A5`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/api/llm_report.py`
- Output:
  - one first-consumer path note
  - one entry decision:
    - graph page pushes to consumer
    - writing/report page pulls prepared graph evidence
    - or a narrow backend bridge prepares the handoff
- Acceptance:
  - the first consumer path names the handoff owner explicitly
  - the handoff does not bypass evidence-pack shaping
  - downstream failure modes are separated from graph submit failure modes
- Module boundary:
  - first consumer integration note only; does not redesign the full writing workbench
- Minimum verification:
  - structural:
    - confirm `api/writing.py` and `api/llm_report.py` remain the downstream entry anchors
  - flow:
    - describe one `graph selection -> evidence pack -> writing/report input` path
    - verify `draft -> submit -> evidence pack -> reporting/writing handoff -> persist -> list/replay` via API route test

## Task A7: Close with Minimum Validation and Phase-1 Readiness

- Goal: Produce the minimum validation checklist that proves the theme is implementation-ready.
- status: pending
- depends_on: `["A1","A2","A3","A4","A5","A6"]`
- blocks: `[]`
- Input:
  - all prior task outputs
  - updated `01` and `02` docs
- Output:
  - one phase-1 readiness checklist
  - one minimum structural validation set
  - one minimum flow validation set
  - one explicit carry-over list for phase 2
- Acceptance:
  - the docs can answer, in order:
    - what is editable
    - what is synchronizable
    - what is auditable
    - what is consumable downstream
  - at least one structural check and one flow check are present
  - phase-2 items are explicitly excluded from phase 1
- Module boundary:
  - development docs only
- Minimum verification:
  - `git diff --check -- development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-graph-editing-and-reporting/01_graph-editing-and-reporting-plan-2026-03-07.md development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-07-graph-editing-and-reporting/02_atomic-tasklist-graph-editing-and-reporting-2026-03-07.md`
