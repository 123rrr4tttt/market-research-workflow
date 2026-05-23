<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/04_wave6-evidence-closure-gap-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/04_wave6-evidence-closure-gap-2026-05-22.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Wave6 Evidence And Closure Gap

Run date: 2026-05-22 PST

Worktree:
`/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave6-parallel-agent-orchestration`

Branch: `codex/devdocs-wave6-parallel-agent-orchestration`

## Scope

This note checks the current closure state of the April parallel-agent
orchestration topic and records the smallest project plan that can be
landed without touching shared integration indexes.

Inputs checked:

- [README.md](./README.md)
- [01_parallel-agent-wave-orchestration-plan-2026-04-07.md](./01_parallel-agent-wave-orchestration-plan-2026-04-07.md)
- [02_subagent-task-contract-template-2026-04-07.md](./02_subagent-task-contract-template-2026-04-07.md)
- [03_wave0-baseline-freeze-task-pool-2026-04-07.md](./03_wave0-baseline-freeze-task-pool-2026-04-07.md)
- [CURRENT_DEV status audit](../../../../../development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/README.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/README.md)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/parallel-plan-tree-2026-05-22.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/parallel-plan-tree-2026-05-22.md)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/worktree-branch-plan.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/worktree-branch-plan.md)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/wave3-worktree-plan-2026-05-22.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/wave3-worktree-plan-2026-05-22.md)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/wave4-worktree-plan-2026-05-22.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/wave4-worktree-plan-2026-05-22.md)
- [../../../../../codex_settings/AGENTS.md](../../../../../codex_settings/AGENTS.md)
- [../../../../../codex_settings/scripts/swarm_file_bootstrap.sh](../../../../../codex_settings/scripts/swarm_file_bootstrap.sh)
- [../../../../../codex_settings/scripts/swarm.sh](../../../../../codex_settings/scripts/swarm.sh)

## Current Status

| Item | State | Evidence | Decision |
|---|---|---|---|
| Topic directory | `not_closed` | 2026-04-07 status audit marks this topic as `not_closed/doc_aligned`; 2026-05-22 folder audit keeps it active as an execution framework, not closure evidence. | Keep in `CURRENT_DEV`; do not archive from this lane. |
| `01` wave plan | `needs_update` | The original Wave 0-5 shape remains useful as a boundary model, but 2026-05-22 produced actual Wave 0-4 integration plans and a separate Wave5 clue-chain plan. | Treat as an orchestration reference, not the current live queue. |
| `02` task contract template | `current` | Required fields still match the worktree-branch plan return contract: result, changed files, validation status, risk. | Keep; use for future branch-level assignments. |
| `03` Wave 0 task pool | `partially_closed_by_later_evidence` | The dev-docs folder audit and branch plans created the shared executable task pool, branch split, gates, and merge policy. | Do not reuse as the active task queue without a status note. |
| Runtime `multi_agent_v1.spawn_agent` | `unclosed_runtime_gap` | Current runtime search did not expose `multi_agent_v1.spawn_agent`; fallback was single Agent plus parallel shell/tool reads. | Record as an environment capability gap, not a repo code gap. |
| Local swarm scripts | `usable_fallback` | `codex_settings/scripts/swarm_file_bootstrap.sh` gives deterministic file context; `swarm.sh` batches bootstrap runs with bounded concurrency. | Use as fallback for file-level exploration, not as proof of real subagent execution. |
| `codex_settings/AGENTS.md` multi-agent naming | `updated_in_this_lane` | The export still used the old `multi-agent-parallel-development` wording. | Updated to name `multi_agent_v1.spawn_agent`, require `tool_search`, and record fallback behavior. |

## Closed Items

- The topic has a stable execution contract for worktree lanes:
  branch, worktree path, owner role, scope, gate, and fixed return
  fields are now represented by the 2026-05-22 branch-plan artifacts.
- The April Wave 0 discovery requirement has practical evidence:
  `worktree-branch-plan.md`, `parallel-plan-tree-2026-05-22.md`,
  and later Wave3/Wave4 plans identify concrete lane ownership and
  lane gates.
- The repo has deterministic fallback tooling for file-level swarm
  inspection through `codex_settings/scripts/swarm_file_bootstrap.sh`.

## Not Closed

- This topic itself is still an active orchestration entry. It should
  not be moved to `ARCHIVE_CLOSED` until a supervisor-level sync updates
  shared indexes and decides whether the April plan is historical or
  still the canonical orchestration entry.
- Real `multi_agent_v1.spawn_agent` availability is not proven in this
  runtime. When unavailable, downstream lanes must explicitly record the
  fallback path instead of claiming subagent execution.
- The April Wave 1-5 plan is stale as a queue because later dev-docs
  waves already executed with different branch names, gates, and
  closure evidence.

## Minimum Development Plan

1. Keep the April topic in `CURRENT_DEV` as the orchestration reference.
2. For any new parallel lane, issue a short contract with:
   `目标`, `边界`, `验收`, `禁止项`, `推荐入口`, `结果`, `改动文件`,
   `验证状态`, and `风险`.
3. Before spawning agents, search for `multi_agent_v1.spawn_agent` when
   it is not already visible. If the tool remains unavailable, record
   the fallback and use parallel shell/tool calls only for read-only
   exploration.
4. Use the 2026-05-22 plan tree, Wave3 plan, Wave4 plan, and Wave5
   clue-chain plan as the current branch-queue evidence instead of
   rerunning the April Wave 0 task pool.
5. Let the main supervisor update shared navigation files:
   `CURRENT_DEV/INDEX.md`, `development-plans/INDEX.md`,
   `README.md`, and `MERGED_OVERVIEW.md`.

## Validation Plan

Minimum checks for this lane:

```bash
git diff --check
bash codex_settings/scripts/swarm_file_bootstrap.sh \
  development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/04_wave6-evidence-closure-gap-2026-05-22.md
```

Changed-doc link check should include this topic directory and
`codex_settings/AGENTS.md` if Markdown links are changed again.

## Residual Risk

- This document does not update shared indexes by design. Until the
  supervisor merges and syncs navigation, discovery of this file depends
  on the topic-local README and direct path.
- Runtime agent capability is environment-dependent. The repo can define
  the orchestration contract and fallback scripts, but cannot by itself
  prove that a future Codex runtime exposes `multi_agent_v1.spawn_agent`.
