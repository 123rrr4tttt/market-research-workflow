# IO Architecture Matrix (Agent Cases)

Date: 2026-03-10 (PST)
Scope: `spec-to-agents`, `openai-agents-js`, `langgraph`

## 1) Stage: Task Intake

Abstract Input:
- `job_id`, `project_key`, `request_payload`, `input_source`, `requested_mode`, `trace_id`

Abstract Output:
- `normalized_input`, `runtime_context`, `entry_node`, `run_mode`, `accepted_at`, `intake_status`

Evidence:
- `spec-to-agents/src/spec_to_agents/console.py`
- `openai-agents-js/packages/agents-core/src/run.ts`
- `langgraph/libs/langgraph/langgraph/graph/state.py`

## 2) Stage: Planning and Handoff

Abstract Input:
- `conversation_items`, `current_agent`, `handoff_candidates`, `route_policy`, `context_ref`, `constraint_set`

Abstract Output:
- `next_agent`, `handoff_payload`, `handoff_reason`, `request_user_input`, `handoff_id`, `handoff_status`

Evidence:
- `spec-to-agents/src/spec_to_agents/workflow/executors.py`
- `openai-agents-js/packages/agents-core/src/handoff.ts`
- `langgraph/libs/langgraph/langgraph/types.py` (`Command.goto`, `Send`)

## 3) Stage: Guardrails / Symbolic Rules

Abstract Input:
- `rule_set_version`, `stage_name`, `candidate_items`, `tool_intent`, `run_context`, `policy_mode`

Abstract Output:
- `allow_or_block`, `blocked_reason`, `rule_hits`, `severity`, `guardrail_report_id`, `post_guard_payload`

Evidence:
- `openai-agents-js/packages/agents-core/src/runner/guardrails.ts`
- `openai-agents-js/packages/agents-core/src/toolGuardrail.ts`
- `langgraph/libs/prebuilt/langgraph/prebuilt/tool_validator.py`

## 4) Stage: Tool Dispatch and Execution

Abstract Input:
- `tool_name`, `tool_args`, `tool_schema`, `approval_policy`, `retry_budget`, `dispatch_trace`

Abstract Output:
- `tool_result`, `tool_error`, `tool_latency_ms`, `tool_status`, `next_step_hint`, `tool_event_id`

Evidence:
- `spec-to-agents/src/spec_to_agents/tools/bing_search.py`
- `openai-agents-js/packages/agents-core/src/runner/toolExecution.ts`
- `langgraph/libs/prebuilt/langgraph/prebuilt/tool_node.py`

## 5) Stage: Runtime State and Checkpoint/Replay

Abstract Input:
- `run_id`, `thread_id`, `checkpoint_id`, `state_snapshot`, `pending_writes`, `resume_policy`

Abstract Output:
- `persisted_state`, `checkpoint_ref`, `resume_state`, `replay_ready`, `state_version`, `checkpoint_status`

Evidence:
- `openai-agents-js/packages/agents-core/src/runState.ts`
- `langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py`
- `langgraph/libs/langgraph/langgraph/pregel/_loop.py`

## 6) Stage: Error, Retry, and DLQ

Abstract Input:
- `failure_stage`, `error_type`, `error_payload`, `retry_count`, `retry_budget`, `idempotency_key`

Abstract Output:
- `retry_decision`, `next_retry_at`, `terminal_failure`, `reason_code`, `dlq_record`, `recovery_hint`

Evidence:
- `spec-to-agents/src/spec_to_agents/workflow/executors.py`
- `openai-agents-js/packages/agents-core/src/runner/turnResolution.ts`
- `langgraph/libs/langgraph/langgraph/pregel/_io.py`

## 7) Stage: Observability

Abstract Input:
- `trace_id`, `span_context`, `event_type`, `stage_name`, `run_metadata`, `timing_source`

Abstract Output:
- `span_tree`, `stage_metrics`, `event_log`, `failure_slice`, `audit_snapshot`, `observability_status`

Evidence:
- `spec-to-agents/src/spec_to_agents/utils/display.py`
- `openai-agents-js/packages/agents-core/src/tracing/spans.ts`
- `openai-agents-js/packages/agents-core/src/tracing/traces.ts`
- `langgraph/libs/langgraph/langgraph/pregel/main.py`

## 8) Canonical Skill Envelope (project-ready)

```json
{
  "status": "ok|fail",
  "data": {},
  "error": {
    "code": "",
    "message": "",
    "details": {}
  },
  "meta": {
    "trace_id": "",
    "project_key": "",
    "skill_name": "",
    "rule_set_version": "",
    "latency_ms": 0
  }
}
```

## 9) Batch Queue + Replay + Handoff Mapping

- Queue lifecycle fields: `job_id`, `item_id`, `queue`, `priority`, `attempt`, `status`, `next_retry_at`.
- Replay fields: `thread_id`, `checkpoint_id`, `resume_from_stage`, `replay_reason`.
- Handoff fields: `handoff_id`, `from_agent`, `to_agent`, `intent`, `constraint_set`, `decision_log`.
- Rule decision fields: `rule_id`, `decision`, `severity`, `reason_code`, `evidence_ref`.

This matrix is the reference source for implementing Phase 0 IO contracts in `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture`.
