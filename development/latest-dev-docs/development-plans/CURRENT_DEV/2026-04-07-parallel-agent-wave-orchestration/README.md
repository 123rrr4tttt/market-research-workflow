# 2026-04-07 Parallel Agent Wave Orchestration

## 文档列表

1. [01_parallel-agent-wave-orchestration-plan-2026-04-07.md](./01_parallel-agent-wave-orchestration-plan-2026-04-07.md)
2. [02_subagent-task-contract-template-2026-04-07.md](./02_subagent-task-contract-template-2026-04-07.md)
3. [03_wave0-baseline-freeze-task-pool-2026-04-07.md](./03_wave0-baseline-freeze-task-pool-2026-04-07.md)
4. [04_wave6-evidence-closure-gap-2026-05-22.md](./04_wave6-evidence-closure-gap-2026-05-22.md)

## 阅读顺序

1. 先读 `01_parallel-agent-wave-orchestration-plan-2026-04-07.md`，确认整个仓库后续并行开发的波次、责任域、门禁和禁止项。
2. 再读 `02_subagent-task-contract-template-2026-04-07.md`，按统一任务契约给子 agent 下发目标、边界、验收和回报格式。
3. 最后读 `03_wave0-baseline-freeze-task-pool-2026-04-07.md`，直接启动 Wave 0 的基线冻结与任务归属核对。
4. 若是在 2026-05-22 之后继续并行开发，先读 `04_wave6-evidence-closure-gap-2026-05-22.md`，确认哪些内容已被后续 worktree 波次替代、哪些仍是未封口能力差距。

## 使用说明

1. 本目录是当前仓库“以子 agent 为主、主 agent 做收口”的默认执行入口。
2. 主 agent 不应在本专题之外重新口述完整设计，而应把子 agent 引导回仓库代码、`CURRENT_DEV` 索引和对应专题文档。
3. 若某个波次已经形成新的冻结结论，应优先在对应专题下补充 closure / validation 文档，再回写本目录引用。
4. 若后续并行编排需要新增示例任务包或参考材料，可在本目录下追加 `references/`，但不应把实际实现文档迁出原专题。
5. 本目录的 2026-05-22 Wave6 证据只更新专题内状态；共享总索引由主代理统一合并。
