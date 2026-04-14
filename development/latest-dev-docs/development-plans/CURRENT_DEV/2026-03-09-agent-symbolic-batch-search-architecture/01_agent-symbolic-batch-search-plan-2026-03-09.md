# Agent + Symbolic + Batch Search Plan

Date: 2026-03-09 (PST)
Owner: backend workflow / search / crawler / llm / frontend-modern
Status: CURRENT_DEV

## 1. Objective

Build one integrated architecture that replaces manual one-by-one search with:
- agent orchestration,
- symbolic rule constraints,
- batch scheduling and replay,
- observable and recoverable execution,
- unified platformization through skill contracts.

## 2. Why This Route

Current repository already has reusable foundations:
- orchestration and runtime: `workflow_graph/*`, `collect_runtime/*`,
- search/source/crawler services: `search/*`, `source_library/*`, `crawlers/*`,
- UI landing zones: `LlmDesignerPage`, `ResourcePage`, `OpsPage`.

Decision:
- Keep existing backend as base,
- Layer symbolic rules + batch scheduler,
- Push toward full skillization as platform default.

## 3. Architecture Scope (single stitched system)

Control plane:
- task intake, rule compile, agent routing, rollout control.

Execution plane:
- workflow execution, tool invocation, retry/idempotency, event emission.

Data plane:
- batch jobs/items, handoff logs, rule versioning, run artifacts.

Guardrails plane:
- tool allowlist, schema validation, symbolic hard constraints.

Observability plane:
- batch/handoff/guardrail metrics and replay-ready event logs.

UI plane:
- operate inside existing frontend pages (no standalone console).

## 4. Phased Rollout

### Phase 0 (priority): Agent runtime foundation deployment

Goal:
- deploy one complete agent runtime before service-by-service migration.

In scope:
- `Agent Orchestrator` runtime baseline
- `Skill Registry` with unified skill envelope
- `Handoff` contract and persistence
- `Symbolic Rule Engine` baseline
- `Batch Queue` baseline and job lifecycle API
- 1-2 built-in smoke skills for runtime validation

Exit criteria:
- end-to-end path works: `submit -> dispatch -> handoff -> result`,
- all runtime stages emit stable envelope and trace fields,
- runtime supports replay for failed batch items.

### Phase 1: Information-collection skillization

Goal:
- convert collection path services to skill contracts on top of Phase 0 runtime.

In scope:
- `skill.search.web`, `skill.search.hybrid`, `skill.search.smart`
- `skill.source.resolve`, `skill.source.run`
- `skill.crawler.dispatch`
- `skill.collect.batch_dispatch`, `skill.collect.aggregate`
- batch submit/list/get/retry APIs and basic queue operations

Exit criteria:
- target use case no longer relies on manual one-by-one search,
- collection batch item is traceable and replayable,
- guardrails can block unsafe collect path calls.

### Phase 2: Workflow and LLM + full service skillization

In scope:
- `skill.workflow.compile`, `skill.workflow.run`, `skill.workflow.events`
- `skill.llm.generate`, `skill.llm.extract_structured`
- remaining core services are routed by default through skill registry
- handoff envelope persistence + rule version pinning.

## 5. Mandatory Gates

1. Crawler args allowlist + schema validation.
2. LLM structured output validation before routing.
3. No silent durable-store to in-memory fallback.
4. Stable reason codes for allow/block/failure paths.
5. Metrics for `batch.*`, `handoff.*`, `guardrail.*`.

## 6. Economic and Feasibility Position

Economic side:
- positive ROI because most capabilities are extension over existing services, not net-new stack rebuild.

Feasibility side:
- high feasibility with phased rollout;
- complexity concentration is controlled by Phase 0-first delivery.

## 7. Deliverables

- one plan doc (this file),
- one atomic tasklist doc,
- indexed links in `CURRENT_DEV` + `development-plans` + top-level snapshots.

## 7.1 Frozen Implementation Decisions (2026-03-10)

1. Compatibility-first envelope:
- keep project-native response contracts backward-compatible;
- new agent/skill paths use canonical `status/data/error/meta`;
- legacy `{ok,data,error}` paths are preserved through adapter wrappers during migration.

2. Skill registry and versioning:
- adopt best-practice namespaced skill IDs: `<domain>.<capability>` (for example `collect.search.web`);
- enforce explicit `contract_version` per skill invocation;
- keep immutable versioned contracts and optional alias routing for migration.

3. Replay mode policy:
- both replay modes are supported: `events_only` and `stateful`;
- default mode is `events_only` for safer rollout; `stateful` is opt-in per workflow.

4. Phase 1 collection scope:
- Phase 1 targets full collection chain enablement (not subset pilot);
- agent must be able to trigger end-to-end `collect -> process -> ingest -> persist`;
- strategy tuning must be first-class (`rule_set`, routing, retry/backoff, provider policy).

## 8. Local Case Harvest Evidence (mandatory grounding)

Local repositories:
- `reference-pool/oss/agent-cases/spec-to-agents` @ `30009fc`
- `reference-pool/oss/agent-cases/openai-agents-js` @ `448b9c2`
- `reference-pool/oss/agent-cases/langgraph` @ `46fed9d`

Reusable anchors:
- workflow orchestration loop and state progression,
- handoff contract and message envelopes,
- guardrail hook points before/after tool execution,
- parallel and batch execution primitives,
- interruption and resume checkpoints.

Verification command:

```bash
for d in spec-to-agents openai-agents-js langgraph; do
  git -C reference-pool/oss/agent-cases/$d rev-parse --short HEAD
done
```

## 9. Full Service-to-Skill Mapping (route you requested)

Skillization target is all core runtime services, grouped by domain:

Search domain:
- `skill.search.web` <- `app/services/search/web.py`
- `skill.search.hybrid` <- `app/services/search/hybrid.py`
- `skill.search.smart` <- `app/services/search/smart.py`

Source domain:
- `skill.source.resolve` <- `app/services/source_library/resolver.py`
- `skill.source.run` <- `app/services/source_library/runner.py`

Crawler domain:
- `skill.crawler.dispatch` <- `app/services/crawlers/bridge.py`
- `skill.crawler.deploy` <- `app/services/crawlers_mgmt/service.py`
- `skill.crawler.rollback` <- `app/services/crawlers_mgmt/service.py`

Workflow domain:
- `skill.workflow.compile` <- `app/services/workflow_graph/compiler.py`
- `skill.workflow.run` <- `app/services/workflow_graph/runtime.py`
- `skill.workflow.events` <- `app/api/workflow_graph.py`

LLM domain:
- `skill.llm.generate` <- `app/services/llm/provider.py`
- `skill.llm.extract_structured` <- `app/services/workflow_graph/executors/llm_call.py`

Resource and collect domain:
- `skill.resource.recommend` <- `app/services/resource_pool/unified_search.py`
- `skill.collect.batch_dispatch` <- `app/services/collect_runtime/runtime.py`
- `skill.collect.aggregate` <- `app/services/collect_runtime/runtime.py`

## 10. API Draft (skill-first orchestration)

New API family (keep old APIs backward-compatible):
- `POST /api/v1/agent-batch/jobs` (submit job)
- `GET /api/v1/agent-batch/jobs/{job_id}` (job summary)
- `GET /api/v1/agent-batch/jobs/{job_id}/items` (item list)
- `POST /api/v1/agent-batch/jobs/{job_id}/retry` (retry failed items)
- `GET /api/v1/agent-batch/jobs/{job_id}/events` (timeline/replay source)
- `POST /api/v1/agent-batch/rule-sets/validate` (rule dry-run)

Response envelope standard:
- `status` (`ok|fail`)
- `data`
- `error` (`code/message/details`)
- `meta` (`trace_id/project_key/latency_ms/rule_set_version`)

## 11. Data Model Draft (minimum required)

Tables:
- `agent_batch_jobs`: one row per batch job.
- `agent_batch_items`: one row per input item and execution status.
- `agent_handoffs`: inter-agent handoff chain for replay/audit.
- `symbolic_rule_sets`: named rule set registry.
- `symbolic_rule_versions`: immutable versions.

Key columns:
- `trace_id`, `project_key`, `idempotency_key`, `status`, `reason_code`, `retry_count`, `started_at`, `finished_at`.

## 12. Guardrails and Security Baseline

Hard requirements:
1. Crawler argument allowlist and schema validation.
2. Domain/IP safety checks to block localhost/private ranges.
3. LLM structured output schema validation before route decisions.
4. No silent fallback from durable store to in-memory for batch state.
5. Every skill call must be traceable (`trace_id`, `skill_name`, `rule_set_version`).

## 13. Rollback Strategy

Rollout switches:
- `agent_batch_enabled` (global/project scope)
- `skill_dispatch_mode` (`shadow|active`)
- `rule_enforcement_mode` (`observe|enforce`)

Rollback procedure:
1. switch `skill_dispatch_mode` to `shadow`,
2. disable `agent_batch_enabled` for impacted projects,
3. keep event and handoff logs for post-mortem,
4. replay failed items after fix.

## 14. Stage-Level IO Architecture (from crawled cases)

Reference source:
- `reference-pool/oss/agent-cases/IO_ARCHITECTURE_MATRIX_2026-03-10.md`

Phase 0 must freeze these stage contracts before implementation:

1. Intake IO:
- Input: `job_id/project_key/request_payload/input_source/requested_mode/trace_id`
- Output: `normalized_input/runtime_context/entry_node/run_mode/intake_status`

2. Handoff IO:
- Input: `conversation_items/current_agent/handoff_candidates/constraint_set/context_ref`
- Output: `next_agent/handoff_payload/handoff_id/handoff_reason/handoff_status`

3. Guardrail IO:
- Input: `rule_set_version/stage_name/candidate_items/tool_intent/policy_mode`
- Output: `allow_or_block/rule_hits/severity/reason_code/post_guard_payload`

4. Tool IO:
- Input: `tool_name/tool_args/tool_schema/approval_policy/retry_budget/dispatch_trace`
- Output: `tool_result/tool_error/tool_latency_ms/tool_status/next_step_hint`

5. State + Checkpoint IO:
- Input: `run_id/thread_id/checkpoint_id/state_snapshot/pending_writes/resume_policy`
- Output: `persisted_state/checkpoint_ref/replay_ready/state_version/checkpoint_status`

6. Retry/DLQ IO:
- Input: `failure_stage/error_type/error_payload/retry_count/retry_budget/idempotency_key`
- Output: `retry_decision/next_retry_at/terminal_failure/reason_code/dlq_record`

7. Observability IO:
- Input: `trace_id/span_context/event_type/stage_name/run_metadata`
- Output: `span_tree/stage_metrics/event_log/failure_slice/audit_snapshot`

Delivery rule:
- any new skill adapter that does not fully map to these IO contracts cannot pass Phase 0 gate.
