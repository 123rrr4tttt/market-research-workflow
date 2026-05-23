<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/42_agent-cooperative-abort-coverage-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/42_agent-cooperative-abort-coverage-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Cooperative Abort Coverage

Date: 2026-05-14
Status: R2 implementation evidence
Mainline: Claude Code level AgentCore reconstruction

## Purpose

This document closes the R2 cooperative-abort breadth item from `41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`.

The goal was to ensure cancel/retry/continue is not only a UI/session affordance. Execution tools that can write project/session state or dispatch background work must observe canceled Agent sessions and stop rather than continuing as successful work.

## Implemented Coverage

### AgentCore Tool Wrappers

Updated file:

- `main/backend/app/services/agent_core/project_tools.py`

Added shared `_abort_requested_result(...)` behavior:

- emits `tool_progress` with `contract_version=agent_core.cooperative_abort.v1`;
- returns a `CoreToolResult(status="canceled")`;
- carries `abort_requested=true`, `session_status`, `skipped_items`, and `dispatched_count`;
- provides a retry hint that points back to `task.continue` or `task.retry`.

Covered execution paths:

- direct projected skill invocation;
- `workflow_graph.run`;
- `ingest.url_pool.submit`;
- `report.generate`;
- existing `ingest.source_library.run` cooperative cancellation remains covered and now shares the same evidence lane.

### URL-Pool Background Task

Updated file:

- `main/backend/app/services/tasks.py`

Added `_agent_session_canceled(...)` at the start of `task_ingest_url_via_source_library`.

When the queued URL-pool task receives an Agent submission marker and the session has already been canceled:

- it does not call `ingest_url_via_source_library_frontdoor`;
- it records an `ingest.url_pool.task_event.v1` event with `status=canceled`;
- it returns a canceled result payload with `abort_requested=true`.

### URL-Pool Status Semantics

Updated file:

- `main/backend/app/services/agent_core/project_tools.py`

`ingest.url_pool.status` now treats canceled task events as not pending and returns:

- `next_gate=url_pool_ingest_canceled_resume_or_retry`;
- writing guidance that the source must not be treated as collected evidence.

## Verification

Focused gate:

```bash
python3 -m py_compile main/backend/app/services/agent_core/project_tools.py main/backend/app/services/tasks.py main/backend/tests/unit/test_agent_core_unittest.py
PYTHONPATH=main/backend pytest -q main/backend/tests/unit/test_agent_core_unittest.py -k "session_cancel or mid_dispatch_cancel or background_task_stops or canceled_task_event or source_library_run_stops_dispatching_after_session_cancel"
```

Result:

```text
8 passed, 50 deselected, 3 warnings
```

Broader AgentCore gate:

```bash
PYTHONPATH=main/backend pytest -q main/backend/tests/unit/test_agent_core_unittest.py main/backend/tests/unit/test_material_ontology_unittest.py main/backend/tests/unit/test_agent_control_tools_unittest.py
```

Result:

```text
67 passed, 3 warnings
```

## Closed R2 Claims

| R2 Claim | Evidence |
| --- | --- |
| Source-library collection stops after session cancellation. | `test_source_library_run_stops_dispatching_after_session_cancel` |
| Workflow graph execution does not invoke downstream skill after session cancellation. | `test_workflow_graph_run_does_not_invoke_skill_after_session_cancel` |
| Direct projected skill invocation does not run after session cancellation. | `test_direct_skill_invocation_does_not_run_after_session_cancel` |
| URL-pool submit does not queue after pre-existing session cancellation. | `test_ingest_url_pool_submit_does_not_queue_after_session_cancel` |
| URL-pool submit does not write submission artifact after mid-dispatch cancellation. | `test_ingest_url_pool_submit_does_not_write_submission_after_mid_dispatch_cancel` |
| URL-pool background task does not run ingest frontdoor after session cancellation. | `test_url_pool_background_task_stops_when_agent_session_is_canceled` |
| Report generation does not write an artifact after session cancellation. | `test_report_generate_does_not_write_artifact_after_session_cancel` |
| URL-pool status reports canceled events as resumable/retryable cancellation, not pending evidence. | `test_ingest_url_pool_status_reads_canceled_task_event_as_not_pending` |

## Remaining Boundary

This closes the current R2 code-scope gap. R1 is closed by `43_agent-live-provider-r1-validation-2026-05-14.md`, and R3 is closed by `44_agent-matrix-capability-execution-r3-2026-05-14.md`.
