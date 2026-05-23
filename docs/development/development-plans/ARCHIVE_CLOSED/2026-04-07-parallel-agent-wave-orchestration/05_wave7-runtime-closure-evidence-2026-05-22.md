<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/05_wave7-runtime-closure-evidence-2026-05-22.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/05_wave7-runtime-closure-evidence-2026-05-22.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Wave7 Runtime Closure Evidence

Run date: 2026-05-22 PST

Status: `partial`

Worktree:
`/Users/wangyiliang/market-research-workflow.worktrees/devdocs-wave7-parallel-runtime`

Branch: `codex/devdocs-wave7-parallel-runtime`

## Scope

This note closes the remaining Wave6 runtime-evidence gap as far as the
current repo and current Codex runtime allow. It does not edit shared
navigation indexes by request.

Inputs checked:

- [README.md](./README.md)
- [01_parallel-agent-wave-orchestration-plan-2026-04-07.md](./01_parallel-agent-wave-orchestration-plan-2026-04-07.md)
- [02_subagent-task-contract-template-2026-04-07.md](./02_subagent-task-contract-template-2026-04-07.md)
- [03_wave0-baseline-freeze-task-pool-2026-04-07.md](./03_wave0-baseline-freeze-task-pool-2026-04-07.md)
- [04_wave6-evidence-closure-gap-2026-05-22.md](./04_wave6-evidence-closure-gap-2026-05-22.md)
- [verify_wave7_runtime_contract.sh](./verify_wave7_runtime_contract.sh)
- [../../../../../codex_settings/AGENTS.md](../../../../../codex_settings/AGENTS.md)
- [../../../../../codex_settings/scripts/swarm_file_bootstrap.sh](../../../../../codex_settings/scripts/swarm_file_bootstrap.sh)
- [../../../../../codex_settings/scripts/swarm.sh](../../../../../codex_settings/scripts/swarm.sh)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/parallel-plan-tree-2026-05-22.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/parallel-plan-tree-2026-05-22.md)
- [../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/worktree-branch-plan.md](../../../../../development/latest-dev-docs/automation-runs/dev-docs-folder-audit-2026-05-22/worktree-branch-plan.md)
- [../2026-05-22-clue-chain-investigation-tool/04_wave5_implementation_evidence-2026-05-22.md](../2026-05-22-clue-chain-investigation-tool/04_wave5_implementation_evidence-2026-05-22.md)

## Runtime Tool Discovery

Current run observation:

- the initially visible runtime tools did not include
  `multi_agent_v1.spawn_agent`;
- `tool_search` was invoked with the search phrase
  `multi-agent spawn_agent subagent parallel agent`;
- the tools exposed after that search were Figma and GitHub tools, not
  `multi_agent_v1.spawn_agent`;
- therefore this run cannot claim real subagent spawning.

Decision:

- this is an environment capability gap, not a repo code gap;
- future lanes may claim real multi-agent execution only when the
  runtime exposes `multi_agent_v1.spawn_agent` and the run records the
  subagent return fields;
- when the runtime does not expose the tool, the correct behavior is
  the fallback already written in `codex_settings/AGENTS.md`.

## Repo Contract Audit

| Surface | Finding | Closure decision |
|---|---|---|
| `codex_settings/AGENTS.md` | Names `multi_agent_v1.spawn_agent`, requires `tool_search` when the tool is absent, and forbids fabricating subagent capability. | Repo instruction contract is sufficient. |
| `02_subagent-task-contract-template-2026-04-07.md` | Required fields still include task metadata, ownership, validation, and fixed return fields. | Contract is current for future real subagent runs. |
| `codex_settings/scripts/swarm_file_bootstrap.sh` | Deterministically reports file metadata, rough symbols, inbound references, same-stem files, and missing-file candidates. | Valid read-only file exploration fallback. |
| `codex_settings/scripts/swarm.sh` | Batches bootstrap calls with bounded concurrency and retries, writing per-target logs/status under `codex_settings/runs`. | Valid batch fallback for file-level inspection; not evidence of real subagent spawning. |
| `verify_wave7_runtime_contract.sh` | Checks the repo contract, topic-local links, required contract fields, and bootstrap fallback behavior. | Added as the repeatable Wave7 self-check. |

## Evidence Rollup

| Evidence | State | Meaning |
|---|---|---|
| April Wave 0-5 plan | superseded as live queue | Still useful as the orchestration reference and boundary model. |
| Dev-docs folder audit plan tree | executed/merged evidence | Later Wave0-Wave4 worktree plans created concrete branch lanes, gates, and merge rules. |
| Wave5 Clue Chain evidence | `wave5_merged` / `verification_passed` | Proves branch-lane implementation and focused gates, but not runtime-level `spawn_agent` availability. |
| Wave6 orchestration note | gap identified | Correctly separated repo fallback from missing runtime agent capability. |
| Wave7 self-check | `partial` | Repo contract and fallback are verifiable; real runtime spawn remains unavailable in this session. |

## Closure Decision

This topic can advance from plain `not_closed` to explicit `partial`.

What is closed:

- the repo-level instruction for when multi-agent work is allowed;
- the requirement to search for `multi_agent_v1.spawn_agent` before
  declaring it unavailable;
- the no-fabrication fallback rule;
- the deterministic file-level swarm fallback;
- the fixed task contract and return format for future workers;
- the topic-local validation script and Markdown link check.

What is not closed:

- real `multi_agent_v1.spawn_agent` execution in this runtime;
- proof that a spawned subagent can complete the required fixed return
  fields in this Codex session;
- shared index status sync, because this Wave7 lane was instructed not
  to edit shared navigation files.

Archive decision:

- do not move the topic to `ARCHIVE_CLOSED` from this lane;
- after supervisor sync is allowed, the shared `CURRENT_DEV` entry can
  be downgraded from `not_closed` to `partial` with this file as the
  evidence anchor;
- full closure requires a later runtime where `multi_agent_v1.spawn_agent`
  is callable and at least one real subagent fanout returns:
  `结果`, `改动文件`, `验证状态`, and `风险`.

## Validation

Minimum repeatable checks:

```bash
bash development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/verify_wave7_runtime_contract.sh
git diff --check
```

Focused fallback check:

```bash
bash codex_settings/scripts/swarm_file_bootstrap.sh \
  development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-07-parallel-agent-wave-orchestration/05_wave7-runtime-closure-evidence-2026-05-22.md
```

Expected result:

- Wave7 contract self-check prints `WAVE7_RUNTIME_CONTRACT_OK`;
- `git diff --check` is clean;
- bootstrap output contains `SWARM FILE BOOTSTRAP` and the Wave7 target
  path.

## Residual Risk

- Runtime capability can change across Codex surfaces. This document
  records only the 2026-05-22 session state.
- `swarm.sh` is intentionally a bootstrap batcher; it should not be
  described as a multi-agent runtime.
- Shared navigation still points at Wave6 until a supervisor lane is
  allowed to edit the excluded index files.
