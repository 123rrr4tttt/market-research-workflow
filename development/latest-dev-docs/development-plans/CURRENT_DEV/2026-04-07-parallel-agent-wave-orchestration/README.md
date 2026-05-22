# 2026-04-07 Parallel Agent Wave Orchestration

## 文档列表

1. [01_parallel-agent-wave-orchestration-plan-2026-04-07.md](./01_parallel-agent-wave-orchestration-plan-2026-04-07.md)
2. [02_subagent-task-contract-template-2026-04-07.md](./02_subagent-task-contract-template-2026-04-07.md)
3. [03_wave0-baseline-freeze-task-pool-2026-04-07.md](./03_wave0-baseline-freeze-task-pool-2026-04-07.md)
4. [04_wave6-evidence-closure-gap-2026-05-22.md](./04_wave6-evidence-closure-gap-2026-05-22.md)
5. [05_wave7-runtime-closure-evidence-2026-05-22.md](./05_wave7-runtime-closure-evidence-2026-05-22.md)
6. [06_wave10-runtime-contract-refresh-2026-05-22.md](./06_wave10-runtime-contract-refresh-2026-05-22.md)
7. [07_wave16-runtime-boundary-closure-2026-05-22.md](./07_wave16-runtime-boundary-closure-2026-05-22.md)
8. [runtime_contract_refresh_2026-05-22.json](./runtime_contract_refresh_2026-05-22.json)
9. [wave16_runtime_boundary_closure_2026-05-22.json](./wave16_runtime_boundary_closure_2026-05-22.json)
10. [verify_wave10_runtime_contract.py](./verify_wave10_runtime_contract.py)
11. [verify_wave16_runtime_contract.py](./verify_wave16_runtime_contract.py)

## 阅读顺序

1. 先读 `01_parallel-agent-wave-orchestration-plan-2026-04-07.md`，确认整个仓库后续并行开发的波次、责任域、门禁和禁止项。
2. 再读 `02_subagent-task-contract-template-2026-04-07.md`，按统一任务契约给子 agent 下发目标、边界、验收和回报格式。
3. 最后读 `03_wave0-baseline-freeze-task-pool-2026-04-07.md`，直接启动 Wave 0 的基线冻结与任务归属核对。
4. 若是在 2026-05-22 之后继续并行开发，先读 `04_wave6-evidence-closure-gap-2026-05-22.md`，确认哪些内容已被后续 worktree 波次替代、哪些仍是未封口能力差距。
5. 若需要判断本专题能否封口，读 `05_wave7-runtime-closure-evidence-2026-05-22.md`，以 `partial` 结论区分 repo 合约已闭合与当前 Codex 运行时未暴露 `multi_agent_v1.spawn_agent` 的剩余缺口。
6. 若需要判断 Wave10 之后的 runtime contract，读 `06_wave10-runtime-contract-refresh-2026-05-22.md` 与 `runtime_contract_refresh_2026-05-22.json`，区分 parent runtime 可用、worker runtime 仍需实际工具暴露验证、fallback 规则可检查这三层边界。
7. 若需要判断 Wave16 是否可由 supervisor 迁档，读 `07_wave16-runtime-boundary-closure-2026-05-22.md` 与 `wave16_runtime_boundary_closure_2026-05-22.json`：本目录只封住仓内 runtime 入口、父 runtime 可用事实和 fallback 约定；worker runtime / spawned-subagent proof 作为 successor，不在本目录误封。

## 使用说明

1. 本目录是当前仓库“以子 agent 为主、主 agent 做收口”的默认执行入口。
2. 主 agent 不应在本专题之外重新口述完整设计，而应把子 agent 引导回仓库代码、`CURRENT_DEV` 索引和对应专题文档。
3. 若某个波次已经形成新的冻结结论，应优先在对应专题下补充 closure / validation 文档，再回写本目录引用。
4. 若后续并行编排需要新增示例任务包或参考材料，可在本目录下追加 `references/`，但不应把实际实现文档迁出原专题。
5. 本目录的 2026-05-22 Wave6 证据只更新专题内状态；共享总索引由主代理统一合并。
6. 本目录的 2026-05-22 Wave7 证据把专题状态推进为 `partial`；共享总索引仍需后续 supervisor lane 按统一导航规则同步。
7. 本目录的 2026-05-22 Wave10 证据把 `external_blocked` 收窄为 worker/subagent runtime proof：parent runtime 可用可以记录，但每个 worker 仍必须以自身实际可调用工具为准，不能伪造子代理能力。
8. 本目录的 2026-05-22 Wave16 证据把仓内 runtime 入口和 parent-runtime availability 记为 `archive candidate`，同时把 worker runtime proof 拆为 successor；共享总索引和实际迁档仍由 supervisor 统一执行。

## 本地验证

```bash
python3 development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration/verify_wave10_runtime_contract.py
python3 development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration/verify_wave16_runtime_contract.py
bash development/latest-dev-docs/development-plans/CURRENT_DEV/2026-04-07-parallel-agent-wave-orchestration/verify_wave7_runtime_contract.sh
```
