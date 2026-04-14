# Topic Closure Matrix: Repo Closure Plan (2026-04-07)

> 日期：2026-04-07
> 范围：`AT-RCL-02 ~ AT-RCL-09`
> 目的：把 repo-level closure 进一步下沉到 topic-level completion judgement
> 结论：`AT-RCL-04` 的 runtime convergence 已补齐；repo-closure topic 现已具备 archive-ready 证据

## 1. Why This Note Exists

在 [06_validation-closure-repo-closure-plan-2026-04-07.md](./06_validation-closure-repo-closure-plan-2026-04-07.md) 中，repo-level regression pack 已经绿色，但当时仍建议保留在 `CURRENT_DEV`，原因是 `AT-RCL-02 ~ AT-RCL-09` 尚未形成统一的 topic-level closure 口径。

本文件的作用就是补这一层：

1. 为每个 topic 写清 authority path。
2. 写清 retained compat surface。
3. 写清 rollback handle。
4. 写清 evidence pack 与 completion decision。

## 2. Topic Closure Matrix

| Topic | Authority path | Retained compat | Rollback handle | Evidence | Decision |
|---|---|---|---|---|---|
| `AT-RCL-02` workflow graph durability | durable compiled artifact registry + existing run store / handoff store | in-memory `_compiled` fallback retained | `workflow_graph_db_store_enabled`, `workflow_graph_db_store_fail_closed`, `_compiled` fallback | workflow graph unit + integration packs green; repo targeted closure pack green | `completed` |
| `AT-RCL-03` workflow graph integrity | integrity report + replay diagnostics on edit/runtime paths | additive diagnostics on current runtime payloads | retain additive-only integrity/report payloads without removing current API shape | workflow graph edit/curated tests green; repo targeted closure pack green | `completed` |
| `AT-RCL-04` agent runtime canonical path | direct `/agent-batch/jobs` submit now projects into the `agent_sessions` session/task/event ledger | `agent_batch`, `workflow_graph`, `skill_runtime`, retry/approval/NL command compat entrypoints remain explicit | compat entrypoints remain callable; direct job registry still exists as additive compat layer | agent runtime convergence pack green + [08_agent-runtime-canonical-path-closure-2026-04-07.md](./08_agent-runtime-canonical-path-closure-2026-04-07.md) landed | `completed` |
| `AT-RCL-05` project-key hard gate | explicit request/project key with effective enforcement mode | fallback resolution in dev/default and observability headers | `project_key_enforcement_mode`, `project_key_require_in_non_dev`, fallback headers/warnings | project-key integration pack green; repo targeted closure pack green | `completed` |
| `AT-RCL-06` llm truthfulness | `capability_truth` on llm-report / writing action responses | route names and payload outer shape unchanged | additive metadata can be ignored by old callers | llm-report + writing unit/integration packs green; repo targeted closure pack green | `completed` |
| `AT-RCL-07` source-library authority split | `authority_output` as explicit authority contract | `terminal_output`, `frontdoor_ingress`, `postprocess_frontdoor`, `legacy_result`, `compat_projection` retained | authority contract is additive; compat fields remain while callers migrate | source-library unit/core/smoke packs green; repo targeted closure pack green | `completed` |
| `AT-RCL-08` frontend render ownership | shared kernel render table for module -> page dispatch | legacy `AppShell` fallback behavior retained, but no second page switch table | `AppShell` fallback remains until later destructive cleanup | frontend lint/build/homepage e2e green | `completed` |
| `AT-RCL-09` legacy hash boundary | canonical modern route hash output via kernel route resolver | `legacyHashByMode`, `parseLegacyHashToMode`, backend html redirects, unknown-route fallback | explicit legacy hash adapter + backend redirect compatibility | frontend lint/graph e2e/ingest smoke green; backend redirect contract green | `completed` |

## 3. Completion Judgement Detail

### 3.1 Topics promoted to `completed`

本轮将以下 topic 提升为 `completed`：

1. `AT-RCL-02`
2. `AT-RCL-03`
3. `AT-RCL-04`
4. `AT-RCL-05`
5. `AT-RCL-06`
6. `AT-RCL-07`
7. `AT-RCL-08`
8. `AT-RCL-09`

判断依据：

1. authority path 已经在代码或契约字段中显式出现。
2. retained compat surface 已明确保留，没有靠“默认行为猜测”维持。
3. rollback handle 已存在，且不是纯口头回退。
4. evidence pack 已在本轮或前序闭环中真实执行并绿色。

### 3.2 Topics retained as `in_progress`

当前无。

原因：

1. `AT-RCL-04` 已从 freeze-only 文档冻结推进到 additive runtime convergence 实现。
2. repo-closure 这一组 topic 当前不再存在缺少 authority path / compat / rollback / evidence 任一项的任务。

## 4. Exit Recommendation Update

更新后的 exit recommendation 是：`archive-ready`

原因：

1. repo closure 主题当前已经不存在残留的 `in_progress` topic。
2. `AT-RCL-04` 的 additive runtime convergence 已有实现、验证和 closure note。
3. 后续如果继续推进，应进入迁档或 destructive-cleanup 决策，而不是继续维持 `CURRENT_DEV` 状态。

## 5. Minimum Validation For This Note

```bash
rg -n "AT-RCL-0[2-9]|completed|in_progress|remain in `CURRENT_DEV`" \
  development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-06-repo-logic-gap-assessment -S
```
