# Claude Agent High-Fidelity Migration Mapping

Updated: 2026-04-25 PST

## Goal

This document maps the Claude Code agent architecture into this repository with the smallest possible amount of re-invention.

The migration rule is:

- `direct-port`: preserve Claude behavior, state machine, and field semantics as-is, then adapt only the runtime substrate.
- `medium-adaptation`: keep Claude behavior, but replace the storage/runtime medium.
- `repo-adapter`: keep the public contract, but route through existing repository entrypoints and compatibility façades.

## Source-to-Target Map

| Claude source | Target repo module | Migration class | Notes |
|---|---|---|---|
| `docs/04-coordinator.md` | `main/backend/app/services/agent_runtime/` | `direct-port` | Keep coordinator/worker split, four-phase flow, and continue-vs-spawn rules. |
| `src/utils/tasks.ts` | `main/backend/app/services/agent_runtime/task_bus.py` | `medium-adaptation` | Move task state, claim/block, owner, and dependency semantics into Postgres-backed task rows. |
| `src/hooks/useTaskListWatcher.ts` | `main/backend/app/services/agent_runtime/watchers.py` | `medium-adaptation` | Replace file watch/store with DB event stream plus polling/SSE/WebSocket projections. |
| `src/hooks/useTasksV2.ts` | `main/frontend-modern/src/pages/ProcessPage.tsx` and a future agent-session ops panel | `medium-adaptation` | Preserve task list UX concepts, but render from session/task/event APIs instead of local file state. |
| `src/services/SessionMemory/sessionMemory.ts` | `main/backend/app/services/agent_runtime/memory.py` | `direct-port` | Keep memory thresholding, periodic extraction, and `memory.md` vs `scratchpad.md` separation. |
| `src/services/tools/toolOrchestration.ts` | `main/backend/app/services/skill_runtime.py` and `main/backend/app/services/agent_runtime/tool_policy.py` | `direct-port` | Preserve read-only parallelism and write serialization semantics. |
| `src/tasks/LocalAgentTask/LocalAgentTask.tsx` | `main/frontend-modern/src/pages/ProcessPage.tsx` and agent-session UI state | `medium-adaptation` | Port progress, activity, and task-summary behavior into API-driven UI state. |
| `src/services/toolUseSummary/toolUseSummaryGenerator.ts` | `main/backend/app/services/agent_runtime/progress.py` | `medium-adaptation` | Generate short summary labels for task progress and event feeds. |
| `src/services/approval/*` and `approval binding` flow | `main/backend/app/services/agent_batch/approval_binding.py` and `main/backend/app/api/agent_batch.py` | `repo-adapter` | Keep existing compatibility endpoints, but persist approvals in the new agent-session store. |
| `agent_batch` loop and dispatch chain | `main/backend/app/api/agent_batch.py` plus `main/backend/app/services/agent_batch/*` | `repo-adapter` | Preserve old entrypoints as façades while the new session runtime becomes the real execution core. |
| `workflow_graph` integration | `main/backend/app/api/workflow_graph.py` and `main/backend/app/services/workflow_graph/store.py` | `repo-adapter` | Route graph-triggered agent work through the new session/task ledger instead of custom per-call orchestration. |
| Claude file task directories and watcher files | `main/backend/app/models/entities.py` plus a new public-schema agent ledger | `medium-adaptation` | Replace file-system task protocol with Postgres tables and event projections. |

## What Is Not Migrated

These are intentionally not cloned into the new agent core:

- Claude CLI / Ink UI components.
- Claude local filesystem watcher as the primary protocol.
- Claude Anthropic SDK bindings.
- Claude feature gate / GrowthBook / remote-only internals.
- Claude mobile / bridge / remote-specific shapes.

## Implementation Boundary

The new repo-side agent core should be treated as the canonical execution path:

- `agent_sessions`
- `agent_tasks`
- `agent_messages`
- `agent_artifacts`
- `agent_events`
- `agent_approvals`

The existing `agent_batch`, `skill_runtime`, and `workflow_graph` stacks remain in place only as compatibility adapters until callers are moved to the session/task APIs.

## Runtime Enforcement Status

The tool orchestration migration now has runtime enforcement in `skill_runtime`:

- `read_only`: invokes directly after role and permission checks.
- `write_shared`: when `agent_session_id` and `agent_task_id` are present, reclaims expired leases and checks the task bus `write_set` before invocation; conflicts append `skill.write_conflict` and reject the invocation.
- `write_external`: without `approval_granted`, creates an approval plus an `approval_wait` task and rejects the current invocation with `approval_required:<approval_id>`.
- `privileged`: follows the same approval path as `write_external`; role checks remain enforced by the skill registration.
- Compatibility default: legacy `write_shared` calls without session/task context remain allowed, while `write_external` and `privileged` calls require approval context or explicit `approval_granted`.
