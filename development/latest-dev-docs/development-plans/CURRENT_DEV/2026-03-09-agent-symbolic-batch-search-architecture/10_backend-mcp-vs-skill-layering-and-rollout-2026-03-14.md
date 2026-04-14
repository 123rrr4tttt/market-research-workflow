# Backend MCP vs Skill Layering and Rollout (2026-03-14)

## 1. Summary

This note defines the next-layer architecture after backend skillization:

1. backend common capabilities should move toward MCP-style tool/resource exposure,
2. backend task-level orchestration should remain in the skill layer,
3. frontend should stay thin and only trigger simple actions/skills instead of owning complex agent logic.

The split is not "frontend vs backend". The split is:

- MCP = reusable tool/resource protocol layer
- Skill = business orchestration and governed capability layer
- Frontend = thin trigger and presentation layer

## 2. Core Decision

### 2.1 MCP is for stable reusable capabilities

Use MCP-style exposure for backend capabilities that are:

1. reusable by multiple agents or clients,
2. tool-like or resource-like,
3. relatively stable in contract shape,
4. not tightly coupled to one planner strategy.

Typical candidates in this project:

- source library query and execution
- search
- workflow graph query / replay / execution status
- document retrieval and evidence fetch
- graph read / write
- process and batch-job inspection

### 2.2 Skill is for orchestrated business actions

Keep skills for capabilities that are:

1. planner-facing,
2. policy-governed,
3. task-oriented instead of tool-oriented,
4. likely to mix multiple backend tools in one action.

Typical candidates in this project:

- `agent_batch.dispatch.source_library_item`
- `agent_batch.dispatch.market_collect`
- natural-language planning
- source-library + web hybrid retrieval
- reporting / evidence-pack assembly
- workflow handoff packaging

### 2.3 Frontend stays thin

Frontend should not become an MCP host for project business logic.

Frontend should only:

1. trigger simple user actions,
2. collect parameters,
3. show result summaries and task status,
4. call backend skills or backend MCP-backed services.

This means:

- frontend simple action = OK
- frontend heavy orchestration = not OK
- frontend business capability ownership = not OK

## 3. Recommended Layer Model

### 3.1 Layer A: MCP-style tool/resource layer

Authoritative backend tools/resources exposed with stable contracts.

Examples:

- `source_library.list_items`
- `source_library.run_item`
- `search.market.query`
- `workflow_graph.get_run`
- `workflow_graph.list_events`
- `document_views.fetch`
- `graph.query`

Responsibilities:

- transport/protocol contract
- stable request/response schema
- tool/resource discovery
- authn/authz boundary
- rate limit / tenancy / audit hooks

### 3.2 Layer B: Skill layer

Governed orchestration over one or more MCP-style capabilities.

Examples:

- `agent_batch.dispatch.source_library_item`
- `agent_batch.dispatch.market_collect`
- `workflow_graph.curated.evidence_pack`
- future: `research.hybrid_collect`
- future: `report.build.market_brief`

Responsibilities:

- planner-visible capability registry
- required permissions
- actor role controls
- agent task manifest
- parameter normalization
- task composition
- compatibility adapters

### 3.3 Layer C: Frontend action layer

Examples:

- `runSourceLibrary(...)`
- `runAgentBatchNlCommand(...)`
- `submitGraphStructuredSearchTasks(...)`

Responsibilities:

- user interaction
- minimal payload shaping
- display state / result rendering
- no hidden orchestration logic

## 4. Mapping Current Project Components

### 4.1 Already in the right skill layer

- `app/services/skill_runtime.py`
- `ingest.dispatch.*`
- `agent_batch.dispatch.*`
- planner prompt + manifest path

These should remain skill-layer concerns.

### 4.2 Good MCP candidates

#### Source library

- list effective items
- list effective channels
- run source-library item
- list source-library task results / terminal output

Why:

- reusable by agent, UI, batch runtime, workflow runtime
- stable tool semantics
- naturally parameterized

#### Search

- keyword / market search
- structured search
- evidence/document fetch by query

Why:

- common retrieval primitive
- likely to be reused by multiple agent workflows

#### Workflow graph

- compile
- run
- get run
- replay handoff
- list events

Why:

- already behaves like a tool system
- rich runtime state suitable for MCP resource access

### 4.3 Not MCP-first for now

- planner loop
- autonomous task augmentation
- batch strategy adjustment
- mixed retrieval policy
- approval binding

These should stay in skill/orchestration layer because they encode project-specific agent behavior, not generic tools.

## 5. Recommended Migration Principle

Do not replace skills with MCP.

Instead:

1. extract stable backend tools/resources first,
2. keep skills as wrappers/orchestrators over those tools,
3. migrate frontend to call thin backend actions only.

Target relation:

- MCP provides the primitive
- Skill composes the primitive
- Frontend triggers the skill

## 6. Concrete Rollout Order

### Wave 1

Build MCP-style contracts for read/query capabilities first:

1. source-library listing
2. search query
3. workflow run inspection
4. batch-job inspection

Reason:

- lowest mutation risk
- easiest to stabilize
- useful immediately for agent grounding

### Wave 2

Expose execution tools:

1. source-library run item
2. market collect
3. workflow run / replay

Reason:

- execution semantics become shareable
- skill layer can shrink to policy/orchestration glue

### Wave 3

Refactor skills to consume MCP-style internal tool interfaces:

1. dispatch skills call tool interfaces instead of raw task internals
2. planner manifest references tool-backed skills
3. runtime observability aligns to tool/resource IDs

## 7. Guardrails

### 7.1 Do not let frontend become orchestration runtime

Frontend can expose a button or simple command action, but should not:

- choose retrieval strategy,
- merge source-library and web plans,
- own approval logic,
- interpret workflow state machines.

### 7.2 Do not flatten skills into raw tools

If a capability needs:

- planner visibility,
- actor-role restrictions,
- policy checks,
- approval checks,
- task manifests,

it should remain a skill even if it eventually calls an MCP-backed tool.

### 7.3 Keep contracts explicit

For every MCP-style capability, define:

1. capability ID
2. input schema
3. output schema
4. auth boundary
5. tenancy rules
6. retry / timeout behavior
7. observability keys

## 8. Immediate Implementation Recommendation

The next practical step is not "full MCP migration".

The next practical step is:

1. define an internal MCP-ready capability inventory,
2. choose the first 3 MCP-style candidates,
3. keep current skills intact,
4. refactor one path end-to-end as proof:
   - source library list
   - source library run
   - workflow run inspection

## 9. Decision Table

| Capability type | Best layer |
|---|---|
| Stable reusable backend tool | MCP-style tool/resource layer |
| Planner-facing governed action | Skill layer |
| User-trigger UI action | Frontend action layer |
| Project-specific retrieval strategy | Skill layer |
| Runtime query/status/evidence fetch | MCP-style tool/resource layer |

## 10. Final Position

For this project:

1. backend should gradually become MCP-backed at the common capability layer,
2. backend should keep simple and governed skills at the orchestration layer,
3. frontend should remain simple-skill / simple-action only.

This gives the cleanest separation of concerns and avoids putting agent intelligence in the wrong layer.
