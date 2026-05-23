# Atomic Tasklist: Agent + Symbolic + Batch Search

Date: 2026-03-09 (PST)
Owner: backend workflow + search + crawler + frontend-modern
Parent: `01_agent-symbolic-batch-search-plan-2026-03-09.md`

## 1. Scope and Deliverable

Goal:
- deliver one operable pipeline from symbolic constraints to batch execution and observable operations.

Deliverable:
- three-phase executable baseline with Phase 0 as agent runtime first.

## 1.1 Decision Freeze (2026-03-10)

1. Envelope policy:
- compatibility with existing project contracts is mandatory;
- all new AT outputs must expose canonical `status/data/error/meta`;
- migration period keeps legacy response adapters to avoid breaking callers.

2. Skill contract policy:
- skill naming follows namespaced best practice: `<domain>.<capability>`;
- each skill call must carry explicit `contract_version`;
- no unversioned skill IO in production path.

3. Replay policy:
- both `events_only` and `stateful` are in scope;
- default replay mode is `events_only`, `stateful` controlled by config switch.

4. Phase 1 rollout policy:
- collection chain is full-scope rollout in Phase 1 (search/source/crawler/collect -> ingest/persist);
- strategy adjustment capability is mandatory in Phase 1 deliverable.

## 2. Atomic Tasks

### Phase 0: Agent runtime foundation (must land first)

### AT-00 Build agent orchestrator baseline
- Target: deploy one complete runtime backbone.
- Input: existing workflow/runtime modules.
- Output: orchestrator entrypoint with runtime loop and stable envelope.
- Acceptance:
  - end-to-end `submit -> dispatch -> handoff -> result`.
  - runtime emits `trace_id` and stage events.
- Minimal gate:
  - orchestrator unit tests.

### AT-00.1 Build skill registry baseline
- Target: central skill discovery and dispatch.
- Input: initial skill contracts.
- Output: skill registry with route and validation hooks.
- Acceptance:
  - unknown skill blocked with explicit reason code.
  - registered skills callable through one dispatcher.
- Minimal gate:
  - registry unit tests.

### AT-00.2 Build handoff persistence and replay
- Target: durable handoff chain.
- Input: planner/retriever/verifier transitions.
- Output: persisted handoff envelope and replay API support.
- Acceptance:
  - handoff chain queryable by job id.
  - failed item replay supported.
- Minimal gate:
  - handoff persistence tests.

### AT-00.3 Build rule engine baseline
- Target: symbolic rule compile and evaluation.
- Input: rule set definitions.
- Output: runtime guard evaluator.
- Acceptance:
  - pre-dispatch allow/block decision available.
  - rule version attached to decision logs.
- Minimal gate:
  - rule engine tests.

### AT-00.4 Build batch queue baseline
- Target: unified job/item lifecycle management.
- Input: batch job request.
- Output: queue states and retry hooks.
- Acceptance:
  - item-level status progression is stable.
  - retry budget is enforceable.
- Minimal gate:
  - queue lifecycle tests.

### AT-00.5 Freeze stage-level IO contracts from case library
- Target: lock intake/handoff/guardrail/tool/state/retry/observability IO schemas.
- Input: `reference-pool/oss/agent-cases/IO_ARCHITECTURE_MATRIX_2026-03-10.md`.
- Output: project canonical IO contract doc and adapter checklist.
- Acceptance:
  - all Phase 0 components reference one IO source of truth.
  - no adapter uses undocumented custom fields.
- Minimal gate:
  - contract schema validation tests.

### Phase 1: Information-collection skillization

### AT-01 Define skill contracts for collection path
- Target: unify request/response envelope for collection services.
- Input: search/source/crawler/collect runtime interfaces.
- Output: contract schemas and reason-code conventions.
- Acceptance:
  - stable `status/data/error/meta` envelope.
  - backward-compatible adapter path for existing `{ok,data,error}` consumers.
  - every collection skill request carries `contract_version`.
  - contract tests for each collection skill.
- Minimal gate:
  - contract unit tests.

### AT-02 Build collection skill adapters
- Target: bridge existing services to skill registry.
- Input: `search/*`, `source_library/*`, `crawlers/*`, `collect_runtime/*`.
- Output: adapters for search/source/crawler/collect skills.
- Acceptance:
  - adapters callable via registry only.
  - output normalization and error mapping complete.
  - full collection chain coverage (`search/*`, `source_library/*`, `crawlers/*`, `collect_runtime/*`, ingest/persist handoff).
- Minimal gate:
  - adapter unit tests.

### AT-03 Add symbolic guardrails to collection calls
- Target: enforce security and contract integrity before execution.
- Input: tool call intent + rule set.
- Output: allow/block with reason code.
- Acceptance:
  - unsafe crawler args blocked.
  - invalid input rejected pre-dispatch.
- Minimal gate:
  - guardrail tests with failure injection.

### AT-04 Implement batch scheduler baseline
- Target: dispatch collection batch items with replay capability.
- Input: batch job request + item list.
- Output: per-item status, retries, idempotent behavior.
- Acceptance:
  - configurable concurrency.
  - retry policy and idempotency key enforced.
  - strategy knobs are runtime-adjustable (`routing`, `retry/backoff`, `provider policy`, `rule_set`).
- Minimal gate:
  - scheduler tests.

### AT-05 Ship batch APIs (collection-first)
- Target: product-facing API for submit/list/get/retry.
- Input: Phase 1 runtime.
- Output: `/api/v1/agent-batch/*` minimal closed loop.
- Acceptance:
  - submit and retry work per-item and per-job.
  - response envelope stable.
- Minimal gate:
  - API contract tests.

### AT-06 Add Phase 1 UI operations
- Target: run and observe collection batches in existing pages.
- Input: batch APIs and metrics payload.
- Output: queue view, timeline, failure reason codes, retry action.
- Acceptance:
  - one-click replay from failed item.
  - no standalone new UI.
- Minimal gate:
  - frontend smoke tests.

### Phase 2: Workflow/LLM and full service skillization

### AT-07 Add workflow/llm skill adapters
- Target: route compile/run/llm operations through skills.
- Input: workflow and llm service modules.
- Output: workflow/llm skill adapters.
- Acceptance:
  - new agent orchestration path does not depend on direct legacy calls.
- Minimal gate:
  - unit + integration tests.

### AT-08 Add handoff contract hardening and persistence completion
- Target: replayable inter-agent execution chain.
- Input: planner/retriever/verifier/synthesizer transitions.
- Output: persisted handoff envelope with versioned constraints.
- Acceptance:
  - full chain restorable for replay and audit.
- Minimal gate:
  - handoff persistence tests.

### AT-09 Add observability and release gates
- Target: production-safe rollout and rollback.
- Input: runtime events + guardrail results.
- Output: dashboard-ready metrics and pre-release checks.
- Acceptance:
  - top failure reasons queryable.
  - rollback drill validated.
- Minimal gate:
  - metrics schema tests + release gate script.

## 3. Execution Sequence

1. AT-00 AT-00.1 AT-00.2 AT-00.3 AT-00.4 AT-00.5
2. AT-01 AT-02
3. AT-03 AT-04
4. AT-05 AT-06
5. AT-07 AT-08
6. AT-09

## 4. Minimal Verification Commands

```bash
bash scripts/test-standardize.sh contract
bash scripts/test-standardize.sh unit
bash scripts/test-standardize.sh integration
bash scripts/pre_release_min_gate.sh
```

## 5. Done Criteria

- Phase 0 runtime foundation is stable and replay-ready.
- Phase 1 collection skillization is production-usable and replayable.
- Full path evolves to skill-first orchestration with guardrails and observability.
- Manual one-by-one search is no longer primary workflow for target use cases.

## 6. Milestone and Acceptance Metrics

M0 (Phase 0 complete):
- runtime closed-loop success ratio `>= 95%` in smoke tests,
- handoff persistence completeness `= 100%`,
- skill registry dispatch success ratio `>= 99%` for registered skills,
- rule-engine decision coverage `>= 95%` of runtime-dispatched steps.

M1 (Phase 1 complete):
- batch submit-to-complete success ratio `>= 85%`,
- replay success ratio on failed items `>= 80%`,
- unsafe crawler dispatch blocked ratio `= 100%`,
- no missing trace id in skill calls.

M2 (Phase 2 complete):
- all new orchestration paths are skill-first,
- handoff replay chain completeness `= 100%`,
- reason code coverage for failures `>= 95%`,
- median batch latency reduced vs manual baseline.

## 7. Suggested Execution Window

Week 1:
- AT-00 to AT-00.5.

Week 2:
- AT-01 to AT-04.

Week 3:
- AT-05 to AT-06 and production gray rollout for collection-first scope.

Week 4:
- AT-07 to AT-09 and full skill-first orchestration validation.

## 8. Implementation Boundaries

Must do:
- preserve existing API compatibility,
- keep envelope stable across all new endpoints,
- wire UI into existing `LlmDesignerPage`, `ResourcePage`, `OpsPage`.

Must not do:
- introduce parallel orchestration framework bypassing current backend contracts,
- add ad-hoc skill return formats,
- allow direct uncapped crawler calls from orchestration layer.
