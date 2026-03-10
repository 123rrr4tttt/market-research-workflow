# 2026-03-09 Agent + Symbolic + Batch Search

状态：CURRENT_DEV（未封口）  
目录：`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-09-agent-symbolic-batch-search-architecture`

## Main Docs

- [01 Plan: Agent + Symbolic + Batch Search](./01_agent-symbolic-batch-search-plan-2026-03-09.md)
- [02 Atomic Tasklist: Agent + Symbolic + Batch Search](./02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md)
- [03 Atomic Task Library Investigation Map (AT-00 ~ AT-09)](./03_atomic-task-library-investigation-map-2026-03-10.md)
- [04 Parallel Execution Playbook (Spark/Codex)](./04_parallel-execution-playbook-spark-codex-2026-03-10.md)

## Key Route

- one complete agent runtime as orchestration core,
- all core services converted into skill contracts,
- collection path lands first, then workflow/llm full skillization,
- UI stays inside existing project pages.
- stage-level IO contracts are frozen from crawled case matrix.

## Frozen Decisions (2026-03-10)

- compatibility-first migration with canonical `status/data/error/meta` + legacy adapter compatibility,
- namespaced skill IDs and explicit `contract_version` are mandatory,
- replay supports both `events_only` and `stateful` (default `events_only`),
- Phase 1 is full collection-chain enablement and includes runtime strategy tuning capability.

## Reference Library

- `reference-pool/oss/agent-cases/README.md`
- `reference-pool/oss/agent-cases/IO_ARCHITECTURE_MATRIX_2026-03-10.md`

## Suggested Read Order

1. `01`（整体验证与分阶段计划，Phase 0 为 Agent 体系基座部署）
2. `02`（原子任务、门禁与验收，按 Phase 0 -> 1 -> 2 执行）
3. `03`（每个 AT 独立爬库调查结果、IO 架构、约束与最小验证）
4. `04`（并行序列、Spark/Codex 分流、波次门禁与落地标准）
