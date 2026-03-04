# CV02 分批迁移队列（2026-03-03）

更新时间：2026-03-03 20:27 PST  
用途：记录 `CURRENT_DEV -> CLOSED_DEV` 分批迁移的最终执行结果。

## 1. 迁移判定口径

仅当以下条件全部满足，才进入“可立即迁移”：

1. 任务状态为 `done`（或已明确封口结论）。
2. 不依赖当前被绕过项（当前仅 `IP03/BIP-05`）。
3. 已有可引用验收证据（测试、脚本输出或运行态记录）。

## 2. 可立即迁移（Batch-A）

1. `2026-03-03-currentdev-gap-register` 系列（已在 `CLOSED_DEV/2026-03-03-gap-register-closure`）。
2. `2026-03-03-global-vectorization-general-foundation`（已在 `CLOSED_DEV`）。
3. `2026-03-03-platformization-first-vectorization`（已在 `CLOSED_DEV`）。
4. `2026-03-02-single-url-first-ingest-allocation-plan`（已迁移为 `CLOSED_DEV/2026-03-02-single-url-first-ingest-allocation-closure`）。
5. `2026-03-01-open-source-platform-integration`（已迁移为 `CLOSED_DEV/2026-03-01-open-source-platform-integration-closure`）。
6. `2026-03-02-source-time-window-smart-timestamp-plan`（已迁移为 `CLOSED_DEV/2026-03-02-source-time-window-smart-timestamp-closure`）。
7. `2026-03-02-graph-node-standardization-a-then-b-plan`（已迁移为 `CLOSED_DEV/2026-03-02-graph-node-standardization-a-then-b-closure`）。
8. `2026-03-02-graph-3d-force-engine-parallel-migration`（本轮迁移为 `CLOSED_DEV/2026-03-02-graph-3d-force-engine-parallel-migration-closure`）。

说明：上述条目已完成迁移，不在本批重复操作，仅作为 `CV02` 基线。

## 3. Batch-B 迁移执行结果（已完成）

1. `2026-03-02-ingest-platformization-assessment/*`  
   已迁移为：`CLOSED_DEV/2026-03-02-ingest-platformization-assessment-closure/*`
2. `2026-03-02-ingest-chain-full-branch-map/*`  
   已迁移为：`CLOSED_DEV/2026-03-02-ingest-chain-full-branch-map-closure/*`
3. `2026-03-02-meaningful-ingest-guardrails-plan/*`  
   已迁移为：`CLOSED_DEV/2026-03-02-meaningful-ingest-guardrails-plan-closure/*`

Batch-B 原子任务映射（执行入口）：
- `ingest-chain-full-branch-map` -> `BCH-01~BCH-05`
- `ingest-platformization-assessment` -> `BIP-01~BIP-05`
- `meaningful-ingest-guardrails-plan` -> `BMG-01~BMG-05`

引用：
- `../CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-taskboard.md`
- `./CV02_IP03_BIP05_BLOCKED_CLOSURE_STRATEGY_2026-03-03.md`

## 4. Blocked 收口策略（IP03/BIP-05）

1. 豁免：`WAIVER-DOCKER-001`（扩展封口编号：`WAIVER-CLOSE-IP03-BIP05-20260303-01`）。
2. 证据：任务板固定记录最近一次 preflight 失败与环境缺项。
3. 追踪：每次批次更新必须刷新 blocked 状态与下一次重试窗口。
4. 解除顺序：`IP03 -> BIP-05 -> CV02`。

## 5. 已执行动作

1. 执行目录迁移（保留 `YYYY-MM-DD-*` 前缀）。
2. 同步更新：
   - `development-plans/INDEX.md`
   - `development-plans/main/index.md`
   - `development/latest-dev-docs/README.md`
   - `development/latest-dev-docs/MERGED_OVERVIEW.md`
3. 执行残留校验：
   - `grep -RIn "<old_path>" development/latest-dev-docs` 结果为 0。

## 6. 当前结论

- `CV02` 当前状态：`done`。  
- Batch-A + Batch-B 均已迁移到 `CLOSED_DEV`。  
- `CURRENT_DEV` 已清空，仅保留目录说明文件。
