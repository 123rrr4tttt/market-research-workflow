# 2026-03-09 Agent + Symbolic + Batch Search

状态：CURRENT_DEV（未封口）  
目录：`development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-09-agent-symbolic-batch-search-architecture`

## Main Docs

- [01 Plan: Agent + Symbolic + Batch Search](./01_agent-symbolic-batch-search-plan-2026-03-09.md)
- [02 Atomic Tasklist: Agent + Symbolic + Batch Search](./02_atomic-tasklist-agent-symbolic-batch-search-2026-03-09.md)
- [03 Atomic Task Library Investigation Map (AT-00 ~ AT-09)](./03_atomic-task-library-investigation-map-2026-03-10.md)
- [04 Parallel Execution Playbook (Spark/Codex)](./04_parallel-execution-playbook-spark-codex-2026-03-10.md)
- [07 Agent Loop Kernel Architecture and Planner Governance](./07_agent-loop-kernel-architecture-and-planner-governance-2026-03-11.md)
- [08 Backend AI Agent Runtime Architecture (Current State)](./08_backend-ai-agent-runtime-architecture-2026-03-11.md)
- [09 Backend Full Skillization Best Practices and Implementation Plan](./09_backend-full-skillization-best-practices-and-implementation-plan-2026-03-11.md)
- [10 Backend MCP vs Skill Layering and Rollout](./10_backend-mcp-vs-skill-layering-and-rollout-2026-03-14.md)
- [11 Agent-Exposed Task Contract Completeness Audit](./11_agent-exposed-task-contract-completeness-audit-2026-03-14.md)
- [12 Search Brief / Critic / Retry Policy and Agent Strategy Selection](./12_search-brief-critic-retry-policy-and-agent-strategy-selection-2026-03-25.md)
- [13 Reference Library: Search Brief / Critic / Retry Implementation](./13_reference-library-search-brief-critic-retry-implementation-2026-03-25.md)
- [14 Atomic Tasklist: Search Brief / Critic / Retry Implementation](./14_atomic-tasklist-search-brief-critic-retry-implementation-2026-03-25.md)
- [15 Multi-Agent Wave Execution Order: Search Brief / Critic / Retry](./15_multi-agent-wave-execution-order-search-brief-critic-retry-2026-03-25.md)

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
5. `07`（P2 架构基线：planner prompt 治理、agent loop 阶段契约与内核化门禁）
6. `08`（当前后端 AI agent 架构总览：分层、运行流、模式驱动检索、治理边界）
7. `09`（后端全量技能化：外部最佳实践、目标架构、迁移波次与门禁）
8. `10`（MCP 层 / Skill 层 / Frontend Action 层分工，后续演进顺序与边界）
9. `11`（面向 Agent 暴露的任务协议完整性审计：false capability、schema drift、收敛原则）
   当前状态补充：已完成第一轮参数透传与 `override_params` allowlist 收口。
   下一阶段建议：引入 `search brief -> critic -> bounded retry`，将搜索参数设计从一次性规划提升为受控迭代策略。

10. `12`（策略选型主文档：以 `search brief / critic / bounded retry` 为主线，补充外部 agent 技术对照）
11. `13`（详细参考库：外部论文、代码锚点、测试锚点、可借鉴点与延期点）
12. `14`（带编号与验证索引的原子任务单：可直接作为实施任务板）

13. `15`（多轮子 agent 并行波次执行顺序：明确哪些任务同轮并发、哪些必须串行、每轮门禁与文件归属）
