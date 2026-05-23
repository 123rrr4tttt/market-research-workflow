<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/06_agent-runtime-v2-project-tool-adapters-2026-05-10.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/06_agent-runtime-v2-project-tool-adapters-2026-05-10.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Runtime V2 Project Tool Adapters

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass advances the P1/P2 tool-adapter gap called out after the M4 workbench slice. The goal is to let the agent inspect project execution surfaces before it asks for high-risk approval or falls back to legacy batch execution.

Implemented:

- Added read-only tool definitions and runtime execution for:
  - `workflow_graph.list`
  - `workflow_graph.inspect`
  - `ingest.status.read`
- Added workflow graph compiled-inventory support to the workflow graph compiler/store layer:
  - `WorkflowGraphCompilerService.list_compiled`
  - `InMemoryCompiledGraphStore.list_compiled`
  - `SqlCompiledGraphStore.list_compiled`
- Added capability-registry entries for the new tools so they appear in `agent_runtime.capability.catalog`.
- Updated goal classification so workflow/ingest fact questions stay on the read-only fast path, while execution verbs such as `运行 workflow graph ...` still enter the governed execution path.
- Updated execute-path capability selection so workflow execution requests first run `workflow_graph.inspect` before requesting `workflow_graph.run` approval.
- Updated execute-path source-library/collection requests to read recent ingest status before requesting `ingest.source_library.run`.
- Added default run-loop inputs for workflow graph list/inspect and ingest status tools.

## Main Files

- `main/backend/app/services/agent_runtime/read_only_tools.py`
- `main/backend/app/services/agent_runtime/capability_registry.py`
- `main/backend/app/services/agent_runtime/run_loop.py`
- `main/backend/app/services/workflow_graph/__init__.py`
- `main/backend/app/services/workflow_graph/store.py`
- `main/backend/tests/unit/test_agent_run_loop_unittest.py`
- `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`

## Validation

Commands run:

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py
```

Result: `15 passed`.

```bash
cd main/backend
./.venv311/bin/python -m pytest -q tests/unit/test_agent_sessions_service_unittest.py tests/integration/test_agent_sessions_api_unittest.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py tests/integration/test_agent_chat_api_unittest.py
```

Result: `37 passed, 11 warnings`.

```bash
cd main/backend
./.venv311/bin/python -m py_compile app/services/agent_runtime/tool_contract.py app/services/agent_runtime/read_only_tools.py app/services/agent_runtime/run_loop.py app/services/agent_runtime/capability_registry.py app/services/agent_runtime/interactive_agent.py app/services/workflow_graph/store.py app/services/workflow_graph/__init__.py tests/unit/test_agent_run_loop_unittest.py tests/unit/test_interactive_agent_runtime_unittest.py
```

Result: passed.

## Mainline Satisfaction Update

- P1 tool adapter coverage improves from read-only source/artifact only to project execution surfaces: workflow graph inventory, workflow graph inspection, and ingest/source-library recent status.
- P2 approval flow is still only partially satisfied: the agent can now inspect before approval, but approval reject/edit, impact diff, write-set locking, and abort remain open.
- S-05 workflow execution is stronger: the runtime can inspect graph shape before `workflow_graph.run` approval.
- S-04 ingest/source-library execution is stronger: the runtime can read recent ingest status before governed execution.

## Remaining Gap

This pass still does not make high-risk tools fully Claude Code-like:

- `workflow_graph.inspect` can read compiled graph shape but does not yet synthesize a user-facing impact diff.
- `ingest.status.read` uses job history and session tasks; it is not yet a complete ingest observability query across every storage backend.
- `task.cancel`, `task.retry`, and `task.continue` are still API actions, not model-callable governed tools.
- Approval remains approve-and-continue only; reject and edit-before-approve are still pending.

## Next Mainline Slice

Proceed to P2/P6:

1. Add approval rejection and edit-before-approve support in backend and frontend.
2. Add fixed scenario replay for S-01, S-02, S-05, and one failure-recovery path.
3. Convert `task.cancel`, `task.retry`, and `task.continue` into governed tools after approval edit/reject semantics are stable.
