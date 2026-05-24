# Atomic Task Library Investigation Map (AT-00 ~ AT-09)

Date: 2026-03-10 (PST)
Scope: Agent + Symbolic + Batch Search
Method: one sub-agent per atomic task, independent repository-level investigation

## 1. Purpose

This file freezes a per-AT investigation baseline to reduce implementation drift:
- each AT has explicit reference libraries,
- each AT has explicit local paths,
- each AT has IO contract focus,
- each AT has anti-degradation constraints,
- each AT has minimum validation commands.

## 2. Global Reference Pool (frozen)

- `reference-pool/oss/agent-cases/spec-to-agents` @ `30009fc`
- `reference-pool/oss/agent-cases/openai-agents-js` @ `448b9c2`
- `reference-pool/oss/agent-cases/langgraph` @ `46fed9d`
- `reference-pool/oss/n8n`
- `reference-pool/oss/temporal`
- `reference-pool/oss/langflow`
- `reference-pool/oss/dify`

Execution freeze from owner decisions (2026-03-10):
1. keep compatibility with project-native contracts while converging new paths to `status/data/error/meta`;
2. use best-practice namespaced skill IDs + mandatory `contract_version`;
3. support both replay modes, default `events_only`, optional `stateful`;
4. Phase 1 enables full collection chain and must include strategy-adjustment capability.

Primary local architecture anchors:
- `main/backend/app/services/workflow_graph`
- `main/backend/app/services/collect_runtime`
- `main/backend/app/services/source_library`
- `main/backend/app/services/ingest`
- `main/backend/app/services/llm`
- `main/backend/app/api`
- `main/frontend-modern/src`

## 3. AT-Level Investigation Atlas

### AT-00 Build agent orchestrator baseline
- Reference libraries:
  - `main/backend/app/services/ingest`
  - `main/backend/app/services/workflow_graph`
  - `main/backend/app/services/collect_runtime`
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/dify`
- IO focus:
  - Input: `trace_id`, `request_key`, `task_type`, `input`, `runtime`, `stage_policy`
  - Output: stable `status/data/error/meta`, ordered stage events, `run_id`, `degradation_flags`
- Anti-degradation:
  - keep envelope stable,
  - enforce stage monotonic transitions,
  - idempotent by `request_key`,
  - no silent exception swallowing,
  - trace continuity for handoff.
- Minimum validation:
  - orchestrator unit tests,
  - success/failure/idempotency migration path tests.

### AT-00.1 Build skill registry baseline
- Reference libraries:
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/agent-cases/spec-to-agents`
  - `reference-pool/oss/dify`
- IO focus:
  - Input envelope: `trace_id/request_id/schema_version/op/payload/meta/options`
  - Output envelope: `status/data/error/meta` with `registry_version`
- Anti-degradation:
  - deterministic routing,
  - unknown skill fail-closed,
  - schema validate before dispatch,
  - idempotent `request_id`,
  - no implicit fallback when disabled.
- Minimum validation:
  - list/get/dispatch tests,
  - unknown-skill + schema-fail tests,
  - replay with same `request_id`.

### AT-00.2 Build handoff persistence and replay
- Reference libraries:
  - `main/backend/app/services/workflow_graph`
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/agent-cases/langgraph`
  - `reference-pool/oss/agent-cases/spec-to-agents`
- IO focus:
  - `POST /handoff`: `contract_version/handoff_id/from_agent/to_agent/payload/decision_log`
  - `POST /replay`: `replay_target/replay_mode/from_seq|from_stage|checkpoint_id`
  - outputs include `replay_id/replayed_events/restored_state_hash`
- Anti-degradation:
  - contract-version gating,
  - event sequence continuity,
  - replay idempotency,
  - atomic write for payload+decision logs,
  - full trace chain (`trace_id/run_id/checkpoint_id`).
- Minimum validation:
  - schema tests,
  - replay consistency tests,
  - missing checkpoint failure-path tests.

### AT-00.3 Build rule engine baseline
- Reference libraries:
  - `main/backend/app/services/workflow_graph`
  - `main/backend/app/services/ingest`
  - `main/backend/app/services/collect_runtime`
  - `reference-pool/oss/temporal`
  - `reference-pool/oss/n8n`
- IO focus:
  - Input: `rule_version/rule_checksum/rule_set/subject/context`
  - Output: `allowed|blocked|error`, `reason_code`, `checks[]`, `quality_score`
- Anti-degradation:
  - compile-time rule graph validation,
  - topo deterministic execution,
  - normalized reason codes,
  - fail-closed for unsupported stage,
  - persistent `rule_version + checksum` in logs.
- Minimum validation:
  - compile/runtime rule tests,
  - gate decision contract tests,
  - contract + unit + pre-release minimal gate.

### AT-00.4 Build batch queue baseline
- Reference libraries:
  - `reference-pool/oss/langflow`
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/agent-cases/langgraph`
  - `main/backend/app/services/tasks.py`
  - `main/backend/app/celery_app.py`
- IO focus:
  - Input: `idempotency_key/job_type/items[]/policy/schedule/trace`
  - Output: `job_status/items_status/summary/checkpoint/events`
- Anti-degradation:
  - idempotent enqueue by key+checksum,
  - monotonic status machine,
  - bounded retries/backoff,
  - checkpoint recoverability,
  - append-only audit events.
- Minimum validation:
  - lifecycle tests,
  - timeout/cancel/retry tests,
  - checkpoint replay tests.

### AT-00.5 Freeze stage-level IO contracts
- Reference libraries:
  - `reference-pool/oss/agent-cases/IO_ARCHITECTURE_MATRIX_2026-03-10.md`
  - `reference-pool/oss/agent-cases/spec-to-agents`
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/agent-cases/langgraph`
- Frozen stages:
  - intake,
  - handoff,
  - guardrail,
  - tool dispatch,
  - checkpoint/state,
  - retry/dlq,
  - observability.
- Anti-degradation:
  - strict field whitelist per stage,
  - `contract_version + schema_hash` mandatory,
  - idempotent stage processing,
  - state/retry monotonic counters,
  - required audit IDs with redaction policy.
- Minimum validation:
  - schema snapshot diffs per stage,
  - end-to-end stage replay.

### AT-01 Define skill contracts for collection path
- Reference libraries:
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/agent-cases/spec-to-agents`
  - `reference-pool/oss/agent-cases/langgraph`
  - `main/backend/app/services/collect_runtime`
  - `main/backend/app/api/ingest.py`
- IO focus:
  - normalized `collect.request` and `collect.response`;
  - preserve existing `CollectRequest/CollectResult` fields and wrap with stable envelope.
- Anti-degradation:
  - unknown flow/channel fail-closed,
  - count fields always numeric,
  - batch metadata consistency,
  - parent status reflects partial failures,
  - keep legacy compatibility path.
- Minimum validation:
  - adapter contract snapshot tests,
  - malformed input tests,
  - ingest API backward-compatible assertions.

### AT-02 Build collection skill adapters
- Reference libraries:
  - `main/backend/app/services/collect_runtime`
  - `main/backend/app/services/source_library`
  - `main/backend/app/services/crawlers`
  - `reference-pool/oss/agent-cases/IO_ARCHITECTURE_MATRIX_2026-03-10.md`
- IO focus:
  - unify skill invoke input for `search/source/crawler/collect`,
  - unify adapter output mapping: `status, inserted, updated, skipped, errors, items, meta, display_meta`.
- Anti-degradation:
  - channel allowlist only,
  - raw provider payload preserved in `meta.raw`,
  - strict status/error mapping,
  - batch aggregation consistency,
  - source-library job lifecycle consistency.
- Minimum validation:
  - unit tests for collect/source handlers,
  - integration for source-library + scrapy + collect runtime,
  - contract gate run.

### AT-03 Add symbolic guardrails to collection calls
- Reference libraries:
  - `main/backend/app/services/collect_runtime`
  - `main/backend/app/services/source_library`
  - `main/backend/app/services/source_library/adapters`
- IO focus:
  - input `execution_policy/provider_hints/routing_context/dry_run/idempotency_key`
  - output `status/errors/provider_results/meta.guardrail/meta.routing`
- Anti-degradation:
  - max input bounds,
  - blocklist precedes allowlist,
  - deterministic routing,
  - controlled fallback reasons,
  - bounded retries and complete metadata.
- Minimum validation:
  - dry-run guardrail matrix,
  - route determinism tests,
  - fallback and batch merge consistency tests.

### AT-04 Implement batch scheduler baseline
- Reference libraries:
  - `main/backend/app/services/collect_runtime`
  - `main/backend/app/services/tasks.py`
  - `main/backend/app/celery_app.py`
  - `reference-pool/oss/temporal/common/tasks`
  - `main/backend/app/api/process.py`
- IO focus:
  - scheduling request: `request_id/batch_key/schedule_meta/deadline`
  - scheduling result: `schedule_id/batch_id/state/attempt_count/result/meta`
- Anti-degradation:
  - preserve existing `CollectRequest -> CollectResult` semantics,
  - full partition no overlap,
  - failed-batch isolation,
  - bounded retry/backoff,
  - scheduler-state mapping to process/task API.
- Minimum validation:
  - partition integrity tests,
  - partial-failure isolation,
  - status projection consistency,
  - queue stress degradation tests.

### AT-05 Ship batch APIs (collection-first)
- Reference libraries:
  - `main/backend/app/contracts`
  - `main/backend/app/api`
  - `main/backend/app/services`
  - `main/backend/app/models/entities.py`
- IO focus:
  - `/api/v1/agent-batch/jobs` submit,
  - `/jobs/{id}` status,
  - `/jobs/{id}/items` list,
  - `/jobs/{id}/retry`,
  - `/jobs/{id}/events`,
  - `/rule-sets/validate`.
- Anti-degradation:
  - preserve response envelope,
  - enforce idempotency key,
  - retry creates additive session (not overwrite),
  - paged list/events only,
  - structured error payload mandatory.
- Minimum validation:
  - 6 endpoint success/failure smoke tests,
  - idempotency replay check,
  - retry traceability checks.

### AT-06 Add Phase 1 UI operations
- Reference libraries:
  - `main/frontend-modern/src/lib`
  - `main/frontend-modern/src/hooks`
  - `main/frontend-modern/src/pages`
  - `main/backend/app/api/process.py`
  - `main/backend/app/contracts/responses.py`
- IO focus:
  - list/detail/log/cancel/retry contracts for process tasks,
  - failure timeline and reason code rendering.
- Anti-degradation:
  - keep envelope compatibility,
  - monotonic UI state transitions,
  - retry endpoint idempotency,
  - stable pagination+sorting,
  - poll rate limits.
- Minimum validation:
  - hooks/component smoke,
  - process page failure+log paths,
  - replay operation end-to-end visibility.

### AT-07 Add workflow/llm skill adapters
- Reference libraries:
  - `main/backend/app/services/workflow_graph`
  - `main/backend/app/services/llm`
  - `main/backend/app/services/collect_runtime`
  - `main/backend/app/services/source_library`
  - `main/backend/app/api/workflow_graph.py`
- IO focus:
  - `skill_invoke` envelope for `workflow_graph.compile/run` and `workflow.llm_call`
  - include routing/audit/agent-boundary metadata.
- Anti-degradation:
  - mandatory identity->permission->routing chain,
  - prompt template input completeness,
  - node result normalized fields,
  - fixed run/node event order,
  - no shadow legacy bypass path.
- Minimum validation:
  - workflow runtime/compiler unit tests,
  - llm platformization unit tests,
  - workflow API integration tests.

### AT-08 Add handoff contract hardening and persistence completion
- Reference libraries:
  - `main/backend/app/services/workflow_graph`
  - `reference-pool/oss/agent-cases/openai-agents-js`
  - `reference-pool/oss/n8n/packages/@n8n/ai-workflow-builder.ee`
  - `main/backend/app/contracts/schemas/writing.py`
  - `main/backend/app/services/writing/primary_loop_service.py`
- IO focus:
  - handoff request: `run_id/contract_version/handoff_id/handoff_mode/graph_context/evidence_pack/consumer/producer`
  - replay response: ordered events/results/handoff payload with backend marker.
- Anti-degradation:
  - strict event sequence monotonicity,
  - handoff IDs immutable and revision monotonic,
  - schema+contract versions mandatory,
  - store backend switch observable,
  - unknown event types fail-closed.
- Minimum validation:
  - runtime and curated service unit tests,
  - writing handoff compatibility tests,
  - workflow handoff API integration tests.

### AT-09 Add observability and release gates
- Reference libraries:
  - `main/backend/app/services/ingest`
  - `main/backend/scripts`
  - `scripts/pre_release_min_gate.sh`
  - `scripts/docker-deploy.sh`
  - `scripts/gates/run_r9_ef_verification_slice.sh`
  - `main/ops/rollback.sh`
- IO focus:
  - `FrontdoorResult`, `MetricsPayload`, reason taxonomy,
  - release gate command and rollback package schemas.
- Anti-degradation:
  - strict schema versioning,
  - bounded metric ratios and sample rules,
  - reason-code taxonomy completeness,
  - release fail-closed,
  - rollback metadata completeness and canary allowlist controls.
- Minimum validation:
  - schema checks for frontdoor/metrics/reason mapping,
  - pre-release and rollback script return-code semantics,
  - ingest unit tests for metrics/retry policies.

## 4. Cross-AT No-Drift Rules

1. Every new adapter and API must emit one stable envelope (`status/data/error/meta` or existing compat envelope), no ad-hoc shape.
2. Every task-level execution must be replay-addressable by `trace_id + run_id|job_id`.
3. Every guardrail or release decision must emit stable `reason_code` and remain queryable.
4. Every retry path must be idempotent and bounded.
5. Every rollout path must keep rollback and legacy compatibility switch.

## 5. Implementation Use Rule

Before coding each AT:
1. pin this file + `02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md` as the execution baseline;
2. verify library paths still exist;
3. freeze AT-specific IO schema in code contracts before implementation;
4. run minimal gate for that AT;
5. only then proceed to next AT.
