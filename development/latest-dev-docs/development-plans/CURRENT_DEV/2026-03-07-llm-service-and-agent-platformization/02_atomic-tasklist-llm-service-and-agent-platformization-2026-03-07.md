# Atomic Task List: LLM Service and Agent Platformization (2026-03-07)

## Execution Status Snapshot

- `A1`: closed-minimal by Wave6-5 evidence; baseline repo anchors are real and no longer greenfield.
- `A2-A4`: closed-minimal by `main/backend/app/services/llm/platformization.py` plus writing/report/workflow consumers.
- `A5-A6`: closed-minimal by the platform consumer boundary table and agent permission boundary.
- `A7`: needs-update; long-horizon framework evaluation should be deferred behind current AgentCore/LLM contract deltas.
- `A8`: closed-minimal for the current validation pack; topic stays in `CURRENT_DEV` until the A7 update and any shared-index integration are handled separately.

Wave6-5 status evidence: `03_wave6-5-status-evidence-and-min-plan-2026-05-22.md`.

## Global Serial-Parallel Rules

- `L0` serial bootstrap: `A1` must finish first. No downstream task should redefine the baseline independently.
- `L1` parallel platform-core:
  - group-1 contract: `A2`
  - group-2 routing/config: `A3`
  - group-3 observability: `A4`
- `L2` serial consumer alignment: `A5` starts only after `A2-A4` are frozen, because consumer mapping depends on shared vocabulary.
- `L3` parallel strategy split:
  - group-1 agent boundary: `A6`
  - group-2 long-horizon framework strategy: `A7`
  - `A7` may start after `A5`, but must not contradict the agent boundary frozen in `A6`.
- `L4` serial closure: `A8` runs after `A1-A7` and consolidates validation and rollout expectations.
- Conflict rule:
  - Anything redefining provider/model/capability/route/trace terminology is serialized through `A2`.
  - Anything redefining project-scope, trace, or audit requirements is serialized through `A4`.
  - Anything redefining "agent" semantics is serialized through `A6`.

## Global Module Boundary

The task list assumes the following boundaries.

- Platform config boundary:
  - owns project-scoped LLM service configuration and normalized provider/model availability.
  - current anchors: `main/backend/app/api/llm_config.py`, `main/backend/app/services/llm/config_service.py`, `main/backend/app/services/llm/config_loader.py`
- Shared invocation boundary:
  - owns provider/model/capability/routing resolution plus request context propagation.
  - current anchors: `main/backend/app/services/llm/provider.py`, `main/backend/app/services/llm/service.py`, `main/backend/app/services/llm/ports.py`, `main/backend/app/services/llm/chains.py`
- Business adapter boundary:
  - owns business intent translation and domain-shaped responses.
  - current anchors:
    - writing: `main/backend/app/api/writing.py`, `main/backend/app/services/writing/llm_action_service.py`
    - report: `main/backend/app/api/llm_report.py`, `main/backend/app/services/llm_report_generator.py`
    - workflow: `main/backend/app/api/workflow_graph.py`, `main/backend/app/services/workflow_graph/executors/llm_call.py`
- Agent/orchestration boundary:
  - owns multi-step packaging on top of stable platform contracts.
  - current anchors: `main/backend/app/services/workflow_graph/*`, `main/frontend-modern/src/pages/LlmDesignerPage.tsx`
- This document does not authorize flattening these boundaries into one generic "agent layer".

## Global Task IO Contract

Each task must declare:

- `goal`: the single thing the task is allowed to freeze;
- `depends_on`: upstream tasks that provide mandatory vocabulary or constraints;
- `input`: repo paths and planning inputs the owner must read;
- `output`: the concrete planning artifact that changes;
- `acceptance`: what must be true when the task is done;
- `minimum_validation`: the smallest structural/process check that prevents planning drift.

## Task A1: Baseline Reconciliation

- goal: Reconcile this theme with actual repo assets so the rest of the plan stops assuming missing platform pieces that already exist.
- status: closed-minimal by Wave6-5 status evidence
- depends_on: `[]`
- blocks: `["A2","A3","A4"]`
- input:
  - `01_llm-service-and-agent-platformization-plan-2026-03-07.md`
  - `main/backend/app/api/llm_config.py`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/api/workflow_graph.py`
  - `main/backend/app/services/llm/*`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/services/workflow_graph/executors/llm_call.py`
  - `main/frontend-modern/src/lib/api/domains/writing.ts`
  - `main/frontend-modern/src/pages/LlmDesignerPage.tsx`
- output:
  - one corrected baseline section
  - one repo-grounded gap list
  - one drift note describing where old assumptions were wrong
- acceptance:
  - the document no longer describes `writing` API/domain or workflow-graph LLM execution as nonexistent
  - the baseline clearly distinguishes existing assets from missing platform glue
- minimum_validation:
  - run one repo-wide grep confirming all cited baseline anchors exist

## Task A2: Freeze Shared Service Vocabulary

- goal: Freeze a shared vocabulary for `provider`, `model`, `capability`, `route`, and `trace` that can describe writing, report, and workflow consumers consistently.
- status: closed-minimal by Wave6-5 status evidence
- depends_on: `["A1"]`
- blocks: `["A5","A6","A7"]`
- input:
  - `main/backend/app/services/llm/provider.py`
  - `main/backend/app/services/llm/service.py`
  - `main/backend/app/services/llm/ports.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/services/workflow_graph/executors/llm_call.py`
- output:
  - one platform concept model
  - one short terminology table with allowed meanings
- acceptance:
  - each term has one primary definition and is not overloaded by business-specific wording
  - the same vocabulary can explain at least:
    - one writing action,
    - one report flow,
    - one workflow graph LLM node
- minimum_validation:
  - perform a table-top walkthrough for the three consumer examples above using the same five terms

## Task A3: Freeze Config and Routing Boundary

- goal: Clarify where configuration ownership stops and routing/runtime decisions begin.
- status: closed-minimal by Wave6-5 status evidence
- depends_on: `["A1"]`
- blocks: `["A5","A7"]`
- input:
  - `main/backend/app/api/llm_config.py`
  - `main/backend/app/services/llm/config_service.py`
  - `main/backend/app/services/llm/config_loader.py`
  - `main/backend/app/services/llm/service.py`
  - `main/backend/app/services/llm/provider.py`
- output:
  - one config-to-runtime boundary note
  - one routing-responsibility matrix
- acceptance:
  - the document states which inputs are project-config-driven versus runtime-request-driven
  - new business consumers have a documented place to request capability without owning provider internals
- minimum_validation:
  - describe one route decision example from config read to runtime call

## Task A4: Freeze Trace and Audit Rules

- goal: Define the minimum trace, request identity, failure metadata, and audit expectations that every business consumer must preserve.
- status: closed-minimal by Wave6-5 status evidence
- depends_on: `["A1"]`
- blocks: `["A5","A6","A8"]`
- input:
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/api/llm_report.py`
  - current response-envelope conventions already used by backend APIs
- output:
  - one trace/audit rule set
  - one minimum response/observability checklist
- acceptance:
  - the plan names the minimum context fields required for debugging cross-layer failures
  - failure metadata is described in a way that can apply to both direct business calls and workflow-triggered calls
- minimum_validation:
  - write one sample request/response context carrying `project_key`, `trace_id`, request identity, and failure/result metadata

## Task A5: Map Platform Consumers and Adapter Responsibilities

- goal: Freeze how existing consumers use the shared platform layer, and which logic stays in business adapters.
- status: closed-minimal by Wave6-5 status evidence
- depends_on: `["A2","A3","A4"]`
- blocks: `["A6","A7","A8"]`
- input:
  - `main/backend/app/api/writing.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/api/workflow_graph.py`
  - `main/backend/app/services/workflow_graph/executors/llm_call.py`
- output:
  - one consumer map for writing/report/workflow
  - one adapter-responsibility table
  - one onboarding checklist for a future graph/ingest/crawler consumer
- acceptance:
  - the plan distinguishes platform capability naming from business action naming
  - at least three current consumers are mapped without collapsing them into one fake generic flow
- minimum_validation:
  - verify each mapped consumer has a clear answer to:
    - who owns business validation,
    - who owns routing,
    - who owns observable metadata

## Task A6: Freeze Agent Position and Permission Boundary

- goal: Define the first supported agent shape and prevent "agent" from becoming an umbrella term for all LLM-driven behavior.
- status: closed-minimal by Wave6-5 status evidence
- depends_on: `["A2","A4","A5"]`
- blocks: `["A7","A8"]`
- input:
  - the shared vocabulary from `A2`
  - the trace/audit rule set from `A4`
  - the consumer map from `A5`
  - `main/backend/app/services/workflow_graph/*`
  - `main/frontend-modern/src/pages/LlmDesignerPage.tsx`
- output:
  - one agent role split:
    - user-facing assistant,
    - orchestration runtime,
    - business capability wrapper
  - one first-stage recommendation naming which role is actually prioritized
  - one permission/audit note
- acceptance:
  - the document selects a primary phase-1 agent shape instead of listing all shapes as equal priorities
  - agent behavior is documented as consuming platform capabilities, not bypassing them
- minimum_validation:
  - describe one allowed agent-assisted flow and one explicitly disallowed cross-domain flow

## Task A7: Define Long-Horizon Framework Evaluation Gate

- goal: Convert long-horizon framework discussion into explicit entry criteria instead of vague roadmap language.
- status: needs-update; defer external framework evaluation behind repo-native contract deltas
- depends_on: `["A2","A3","A5","A6"]`
- blocks: `["A8"]`
- input:
  - platform contract outputs from `A2-A5`
  - agent boundary from `A6`
  - local external references already cited by the plan such as `reference-pool/oss/dify/*` and `reference-pool/oss/langflow/*`
- output:
  - one evaluation checklist for external framework fit
  - one reject/defer rule for premature integration
- acceptance:
  - the document states when an external framework is additive versus duplicative relative to the existing facade and workflow graph runtime
  - the document does not commit to immediate adoption without a proven contract gap
- minimum_validation:
  - compare one required framework capability against one repo-native capability and document the delta

## Task A8: Close the Minimum Validation Pack

- goal: Produce the smallest validation set that later implementation work can execute to confirm the plan still matches the repo.
- status: closed-minimal by Wave6-5 validation pack
- depends_on: `["A4","A5","A6","A7"]`
- blocks: `[]`
- input:
  - all outputs from `A1-A7`
  - current repo path inventory used by this theme
- output:
  - one structural validation checklist
  - one process validation checklist
  - one implementation-facing smoke list
- acceptance:
  - the validation pack covers:
    - config/read path,
    - business consumer path,
    - workflow/orchestration path,
    - failure/trace path
  - later implementers can use it without reinterpreting the whole theme from scratch
- minimum_validation:
  - ensure every checklist item points back to a named layer or consumer from earlier tasks
