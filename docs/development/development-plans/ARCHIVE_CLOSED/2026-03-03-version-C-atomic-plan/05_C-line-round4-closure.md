<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/05_C-line-round4-closure.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/05_C-line-round4-closure.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# C线第4轮封口文档（夜间连续迭代）

## 1) 目标范围
- 在 `feature/version-C-streamplus` 主干策略下，完成 C 线第4轮“先检索、再计划、后实现、再验证”的闭环。
- 目标能力：
  - pre-release 分层执行（collect/check/report/publish）
  - 结构化报告四件套自动产出
  - 最小可观测静态校验（trace 关联）

## 2) 实际改动
- 新增知识池沉淀：
  - `信息源库/global/research/2026-03-03-C-line-round4-best-practices.md`
- 新增开发与任务编排文档：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/04_C-line-round4-plan-and-atomic-tasks.md`
- 新增实现：
  - `scripts/pre_release_pipeline.sh`
  - `scripts/pre_release_report_bundle.py`
- 新增验证用例：
  - `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`
- 生成产物（验证阶段输出）：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/artifacts/pre-release-round4/gate-result.json`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/artifacts/pre-release-round4/quality-metrics.json`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/artifacts/pre-release-round4/observability-check.json`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-03-version-C-atomic-plan/artifacts/pre-release-round4/release-notes.md`

## 3) 验证证据
- 执行：`./scripts/pre_release_pipeline.sh`
  - 结果：PASS（lint 因 node_modules 缺失为 SKIP，后端 gate 通过）
  - 证据：四件套报告文件完整生成
- 执行：`python3 -m pytest -q main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`
  - 结果：`1 passed`

## 4) 回滚点
- 代码回滚建议锚点：本轮提交前的 `feature/version-C-streamplus` HEAD。
- 文件级回滚最小集合：
  - `scripts/pre_release_pipeline.sh`
  - `scripts/pre_release_report_bundle.py`
  - `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`
  - `04_C-line-round4-plan-and-atomic-tasks.md`
  - `05_C-line-round4-closure.md`
  - `信息源库/global/research/2026-03-03-C-line-round4-best-practices.md`

## 5) 剩余风险
- lint 当前为 SKIP（未安装 frontend 依赖），仍存在前端静态检查盲区。
- observability 检查为轻量静态校验，未覆盖运行时链路质量（采样率、跨度完整性）。
- API import guard 仍有历史告警（warn-only），尚未进入 blocking。

## 6) 下一轮衔接
- 将 `pre_release_pipeline.sh` 接入 CI（建议 reusable workflow），并将四件套作为 workflow artifact。
- 增加 `--strict` 夜间例行门，逐步从 warn-only 迁移到 blocking。
- 扩展 observability-check 为“静态 + 运行时样本检查”双通道。
