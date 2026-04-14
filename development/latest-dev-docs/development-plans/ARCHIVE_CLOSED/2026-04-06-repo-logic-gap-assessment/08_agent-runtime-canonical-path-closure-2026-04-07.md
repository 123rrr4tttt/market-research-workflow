# Agent Runtime Canonical Path Closure: Repo Closure Plan (2026-04-07)

> 日期：2026-04-07
> 主题：`AT-RCL-04`
> 结论：`/agent-batch/jobs` direct submit path now projects into the `agent_sessions` session/task/event ledger by default, while retry / approval / NL-command surfaces remain explicit compat adapters.

## 1. Purpose

本文件用于给 `AT-RCL-04` 留下 additive runtime convergence 的实现留痕，回答三件事：

1. canonical submit path 是否已经不再只是文档冻结，而是有真实 runtime 投影。
2. `agent_batch` direct job API 是否已经把 session/task/event ledger 作为权威记录链。
3. 保留的 compat surface 和 rollback handle 是否仍然清晰。

## 2. Runtime Convergence Landed

本轮实现落点：

1. `POST /agent-batch/jobs` 在 direct submit 时，除了写入 `_BATCH_JOB_REGISTRY`，还会通过 `project_agent_batch_job_submission(...)` 创建一条 compat session，并返回 additive `session_id` / `current_phase`。
2. `GET /agent-batch/jobs/{job_id}`、`/items`、`/events` 在读取 celery/runtime snapshot 时，会通过 `project_agent_batch_job_state(...)` 把 item/task 状态反投影回 `agent_sessions`。
3. direct job item 现在会被映射成 implementation tasks，batch job 聚合状态会被映射成 verification task，session memory artifact 也随投影同步刷新。
4. `POST /agent-batch/nl-command` 仍然保留 planner loop 语义，但最终仍合流到 `submit_agent_batch_job`，没有再形成第二条同级 submit 主链。

这意味着当前主链已经从“freeze-only canonical path”推进到“compat entrypoint -> canonical session ledger”的 additive convergence。

## 3. Retained Compat Surface

本轮没有做 destructive cutover，以下 compat surface 仍显式保留：

1. `_BATCH_JOB_REGISTRY` 和现有 job API payload 外形。
2. `POST /agent-batch/jobs/{job_id}/retry`
3. `/agent-batch/approvals/*`
4. `POST /agent-batch/nl-command`
5. `POST /agent-batch/nl-command/direct`
6. `workflow_graph.curated.*`

当前回退句柄仍然清晰：

1. direct job API 仍可继续依赖现有 job registry 读取，不要求调用方立即切换到 session API。
2. compat session projection 是 additive 的；若后续需要停止默认投影，可以先回退 projection path，而不是先删除 compat entrypoints。

## 4. Validation

### 4.1 Unit pack

```bash
cd main/backend && .venv311/bin/python -m pytest -q \
  tests/unit/test_agent_batch_api_unittest.py \
  tests/unit/test_agent_sessions_service_unittest.py
```

结果：

1. `44 passed`

### 4.2 Integration pack

```bash
cd main/backend && .venv311/bin/python -m pytest -q \
  tests/integration/test_agent_batch_workflow_closure_unittest.py \
  tests/integration/test_agent_sessions_api_unittest.py
```

结果：

1. `5 passed`

### 4.3 What these packs prove

1. direct `/agent-batch/jobs` submit returns a stable `session_id` and idempotency reuse keeps the same compat session.
2. celery/runtime snapshots now project back into `agent_sessions` task states instead of leaving the ledger stale.
3. job events still expose compat task events while also surfacing projected session events, so old consumers are not silently broken.

## 5. Completion Decision

`AT-RCL-04` 可提升为 `completed`。

判断依据：

1. authority path 已经从“文档定义”变成“direct submit -> session/task/event ledger”的真实实现。
2. retained compat surface 仍然显式存在，没有靠隐含默认行为维持。
3. minimum validation pack 已真实执行并绿色。

## 6. Repo-Level Impact

本文件落地后，这组 repo closure topic 的 `AT-RCL-01 ~ AT-RCL-11` 已全部具备 completed 证据。

因此更准确的仓库级判断不再是“remain in CURRENT_DEV because AT-RCL-04 is still open”，而是：

1. repo closure topic 已达到 archive-ready 状态。
2. 若要做后续动作，应进入文档迁档与 destructive-cleanup 决策，而不是继续把本主题当作未封口开发任务。
