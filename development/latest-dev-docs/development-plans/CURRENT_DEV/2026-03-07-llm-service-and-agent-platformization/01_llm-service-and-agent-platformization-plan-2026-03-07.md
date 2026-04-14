# LLM Service and Agent Platformization Plan (2026-03-07)

> Date: 2026-03-07
> Scope: multi-provider LLM service, shared invocation boundary, agent positioning, long-horizon framework strategy
> Status: planning document; align the theme with current repo reality before any broader implementation split

## 1. Goal

This theme is not about "adding more model vendors".

Its first-stage goal is to turn the repo's existing LLM-related pieces into a platform-shaped layer that can be consumed consistently by multiple product surfaces.

The document should freeze five things:

1. what counts as the shared LLM service layer;
2. where provider/model/capability/routing decisions belong;
3. how trace and audit metadata should flow across business calls;
4. what "agent" means in this repo and what it does not mean yet;
5. how long-horizon agent frameworks are evaluated without becoming the immediate delivery path.

## 2. Current Baseline

### 2.1 Repo assets that already exist

The repo already has concrete LLM-adjacent building blocks. This theme must build on them instead of describing the area as greenfield.

- Shared LLM service internals already exist under:
  - `main/backend/app/services/llm/provider.py`
  - `main/backend/app/services/llm/service.py`
  - `main/backend/app/services/llm/ports.py`
  - `main/backend/app/services/llm/chains.py`
  - `main/backend/app/services/llm/config_loader.py`
  - `main/backend/app/services/llm/config_service.py`
- Business-facing writing actions already exist under:
  - `main/backend/app/api/writing.py`
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/services/writing/template_service.py`
  - `main/backend/app/services/writing/search_suggest_service.py`
  - `main/frontend-modern/src/lib/api/domains/writing.ts`
- Report generation already consumes LLM capabilities:
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
  - `main/backend/app/services/llm_report_source_enrichment.py`
- Workflow-oriented LLM execution already exists under:
  - `main/backend/app/api/workflow_graph.py`
  - `main/backend/app/services/workflow_graph/runtime.py`
  - `main/backend/app/services/workflow_graph/executors/llm_call.py`
  - `main/frontend-modern/src/pages/LlmDesignerPage.tsx`
- Project-scoped LLM config APIs already exist:
  - `main/backend/app/api/llm_config.py`
  - `main/backend/app/services/llm/config_service.py`

### 2.2 What the baseline implies

The repo is already beyond "single page calls one model".

It already contains:

- project-level LLM configuration;
- reusable backend LLM service primitives;
- at least three business consumers of model capability:
  - writing,
  - report generation,
  - workflow graph execution;
- frontend surfaces that expose model-related operations.

So the real problem is coordination, not initial adoption.

### 2.3 Current gaps

Despite the existing assets, platformization is still incomplete.

The main gaps are:

- no single documented service-layer contract across writing, report, and workflow consumers;
- routing responsibility is still hard to reason about across config, business service, and workflow executor layers;
- trace and audit expectations are visible in some paths, but not yet documented as one platform rule set;
- "agent" is still overloaded:
  - it could mean user-facing assistant,
  - orchestration runtime,
  - or business capability wrapper;
- long-horizon frameworks are not yet framed as staged evaluation criteria tied to current repo abstractions.

## 3. Requirement Clarification

### 3.1 What this theme must answer

This theme must make the following questions executable:

- Which layer owns provider selection and model selection?
- Which fields are mandatory for every business-to-LLM call?
- Which concerns belong to the shared platform layer versus business adapters?
- Which responsibilities can be called "agent" in phase 1, and which remain out of scope?
- When is an external long-horizon framework worth evaluating against existing repo runtime pieces?

### 3.2 Primary consumers

The first consumers that must be supported explicitly are:

1. writing actions and template-driven assistance;
2. report generation and source-enrichment flows;
3. workflow graph `llm_call` execution;
4. future ingest/crawler/graph consumers that should reuse the same contract instead of cloning model-call logic.

### 3.3 Definition of platformization in this repo

For this repo, "platformization" should mean:

- shared config and provider registry remain centralized;
- business domains call a stable facade instead of each inventing transport and metadata rules;
- trace, request identity, project scope, and failure shape are documented consistently;
- orchestration consumers can reuse the same invocation contract without bypassing audit rules.

It should not mean "replace all existing business services with a brand-new framework".

## 4. Scope and Non-Goals

### 4.1 In scope

This document should guide first-stage work on:

- shared platform concepts:
  - provider,
  - model,
  - capability,
  - route,
  - trace,
  - audit metadata;
- the boundary between config APIs, backend LLM services, and business-facing action services;
- the adapter relationship between the shared platform layer and existing consumers:
  - writing,
  - llm report,
  - workflow graph;
- the position of agent capabilities relative to the shared service layer;
- staged strategy for long-horizon framework evaluation.

### 4.2 Non-goals

This theme does not, in this stage, commit to:

- full autonomous-agent product delivery;
- replacing current writing/report/workflow implementations end-to-end;
- locking a permanent provider matrix;
- rewriting every prompt and every business action into a new abstraction at once;
- making external frameworks the default runtime path before the current service contract is frozen.

## 5. Recommended Layering

The recommended structure is a layered model, not a new product silo.

### 5.1 Layer A: Config and registry boundary

Purpose:

- manage project-scoped provider/model configuration;
- expose normalized configuration to runtime consumers;
- keep provider onboarding and enable/disable state in one place.

Current repo anchors:

- `main/backend/app/api/llm_config.py`
- `main/backend/app/services/llm/config_service.py`
- `main/backend/app/services/llm/config_loader.py`

### 5.2 Layer B: Shared invocation facade

Purpose:

- provide a stable platform-facing call contract;
- resolve provider/model/capability/routing inputs;
- standardize request context:
  - `project_key`,
  - `trace_id`,
  - request identity,
  - failure shape,
  - observability metadata.

Current repo anchors:

- `main/backend/app/services/llm/service.py`
- `main/backend/app/services/llm/provider.py`
- `main/backend/app/services/llm/ports.py`
- `main/backend/app/services/llm/chains.py`

This layer is the main platformization target.

### 5.3 Layer C: Business action adapters

Purpose:

- translate business intent into platform capability calls;
- keep domain-specific validation and output shaping near the business surface;
- avoid leaking provider-specific or transport-specific details to product APIs.

Current repo anchors:

- writing:
  - `main/backend/app/services/writing/llm_action_service.py`
  - `main/backend/app/api/writing.py`
- report:
  - `main/backend/app/api/llm_report.py`
  - `main/backend/app/services/llm_report_generator.py`
- workflow graph:
  - `main/backend/app/services/workflow_graph/executors/llm_call.py`
  - `main/backend/app/api/workflow_graph.py`

### 5.4 Layer D: Agent and orchestration layer

Purpose:

- package multi-step reasoning or tool-use flows on top of stable platform capabilities;
- remain constrained by project scope, audit requirements, and business permissions;
- reuse the shared invocation facade instead of bypassing it.

Phase-1 recommendation:

- treat agent as a controlled orchestration consumer, not a free-form super-layer;
- allow user-facing assistant and workflow-oriented orchestration to be described separately;
- avoid pretending they are the same runtime concern.

### 5.5 Layer E: Long-horizon framework evaluation

Purpose:

- evaluate whether external agent frameworks add clear value beyond the current facade and workflow graph runtime;
- define entry criteria before integration work begins.

This layer is strategy only in phase 1.

## 6. Implementation Order

The recommended order is intentionally conservative.

### Phase 1: Freeze the platform contract

Must complete:

1. baseline reconciliation against actual repo assets;
2. one platform-facing concept model for provider/model/capability/route/trace;
3. one clarified boundary for config vs shared invocation vs business adapter;
4. one uniform trace/audit expectation for business consumers.

Why first:

- without this, any agent discussion remains ambiguous;
- business domains will continue to diverge in call shape and observability.

### Phase 2: Normalize business adapter entry points

Must complete:

1. map how writing, report, and workflow graph consume the shared layer;
2. identify what is platform-level versus business-level capability naming;
3. document the minimal onboarding contract for a new consumer such as graph/ingest/crawler.

Why second:

- this is the earliest point where "shared platform" becomes testable across more than one domain.

### Phase 3: Freeze agent role split

Must complete:

1. define user-facing assistant versus orchestration runtime versus business wrapper;
2. decide which one is the first supported agent shape;
3. document permission and audit boundaries for that shape.

Why third:

- agent design is only useful after platform invocation rules are stable.

### Phase 4: Evaluate long-horizon framework fit

Must complete:

1. define evaluation criteria against the existing facade and workflow graph runtime;
2. state when an external framework is additive rather than duplicative;
3. keep adoption conditional on proven gaps, not concept preference.

## 7. Parallel and Serial Relations

### 7.1 Serial dependencies

These items should stay serial:

- baseline reconciliation before any new platform abstraction is frozen;
- shared invocation contract before agent positioning;
- agent positioning before long-horizon framework recommendations.

### 7.2 Safe parallel work

These items can be refined in parallel after the baseline is frozen:

- config/routing boundary analysis;
- trace/audit rule consolidation;
- business-consumer mapping for writing/report/workflow graph.

### 7.3 File-boundary coordination rule

If the theme later expands into implementation tasks, changes touching the following areas should not be planned as simultaneous conflicting edits:

- `main/backend/app/services/llm/*`
- `main/backend/app/api/llm_config.py`
- `main/backend/app/services/writing/llm_action_service.py`
- `main/backend/app/services/workflow_graph/executors/llm_call.py`
- `main/backend/app/api/llm_report.py`

## 8. Minimal Validation

This theme should define validation before broader execution starts.

### 8.1 Structural validation

At minimum, the resulting plan should be able to explain all of the following with one consistent vocabulary:

- writing LLM action flow;
- report generation flow;
- workflow graph `llm_call` flow.

### 8.2 Process validation

At minimum, the resulting plan should produce:

- one documented end-to-end request context example containing:
  - `project_key`,
  - `trace_id`,
  - capability,
  - route decision,
  - observable result or failure metadata;
- one consumer-onboarding checklist for a new business domain.

### 8.3 Implementation-facing validation hooks

When this topic is converted into code work, the minimal verification set should include at least:

- one config/read path check for `llm_config`;
- one business-path check for `writing` or `llm_report`;
- one orchestration-path check for `workflow_graph`;
- one failure-path check proving trace/audit fields remain inspectable.

## 9. Risks and Open Questions

### 9.1 Main risks

- If platform vocabulary is frozen without reconciling current repo paths, the document will drift from reality immediately.
- If business adapters keep owning routing logic independently, provider and audit behavior will diverge.
- If "agent" is left ambiguous, later tasks will mix UI assistant work, workflow runtime work, and cross-domain automation under one label.
- If long-horizon framework discussion becomes the main storyline too early, the repo may skip the harder but necessary service-boundary cleanup.

### 9.2 Open questions

- Which routing decisions must remain project-config-driven, and which may be policy-driven at runtime?
- Should workflow graph `llm_call` be treated as a first-class consumer of the same facade, or as a partially separate runtime integration point?
- What is the minimum observable metadata every business action must return to remain debuggable?
- Which agent shape has the strongest phase-1 business pull:
  - user-facing writing assistant,
  - workflow-oriented orchestrator,
  - or a thin business-wrapper role?
