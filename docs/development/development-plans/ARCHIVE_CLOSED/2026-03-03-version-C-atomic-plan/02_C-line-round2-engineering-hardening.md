<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/02_C-line-round2-engineering-hardening.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-C-atomic-plan/02_C-line-round2-engineering-hardening.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# 02 C线第2轮工程化增强记录（工程完备度）

## 1) 本轮目标与范围
- **轮次/线路**：C线第2轮
- **目标**：在不破坏既有行为前提下，补一项工程化增强并给出可执行验证证据。
- **选择项**：最小发布前检查脚本（lint/test gate）
- **选择理由**：
  1. 对业务代码零侵入，不改运行时主链路；
  2. 能快速形成发布前一致检查入口，减少“本地可跑/发布失败”偏差；
  3. 可渐进增强（quick/full/strict），适配当前仓库存量问题。

## 2) 原子任务执行顺序与实际偏差
- 计划原子顺序：
  1. 定位C线工作目录与当前分支；
  2. 新增最小 gate 脚本（quick 默认）；
  3. 执行脚本并记录结果；
  4. 根据执行结果修正脚本健壮性；
  5. 再次执行并固化证据；
  6. 更新 CURRENT_DEV 文档与索引；
  7. 本地提交里程碑。
- 实际偏差：
  - 第一次执行失败（`.venv311` 缺少 pytest）；已在脚本中加入解释器回退逻辑（优先 `.venv311`，无 pytest 时回退 `python3`）。
  - 第二次执行在 API import guard 处因仓库既有问题失败；为避免阻断当前发布前最小门禁，改为默认 warn-only，新增 `--strict` 可切换为阻断模式。

## 3) 改动文件清单与关键设计点
- 新增文件：
  - `main/backend/scripts/pre_release_gate.sh`
- 关键设计点：
  - `--full`：扩展测试集；默认 `quick` 走最小验证路径。
  - `--strict`：将 API import guard 变为阻断；默认非阻断仅告警。
  - Python 解释器策略：优先 `.venv311/bin/python`，若无 pytest 自动回退到 `python3`。
  - 检查顺序固定为：
    1) `compileall app/` 语法烟测；
    2) 目标单测集合；
    3) API import guard。

## 4) 测试命令与 pass/skip/fail 结果
- 执行命令：
  - `./scripts/pre_release_gate.sh`
- 结果（最终一次）：
  - step1 `compileall app/`：**PASS**
  - step2 `pytest -q tests/unit/test_streamplus_contracts_unittest.py tests/unit/test_collect_runtime_process_fallback_unittest.py`：**PASS**（`4 passed, 2 skipped`）
  - step3 `scripts/check_api_layer_imports.py`：**WARN**（存量问题，默认非阻断）
  - gate 总体：**PASS**
- 历史一次失败（已修复）：
  - 失败原因：`.venv311` 无 pytest（`No module named pytest`）
  - 修复：增加解释器回退逻辑。

## 5) 回滚点 commit
- 本轮执行前回滚点（安全回退基线）：`e83f2cf19d3e5648d4265fb9bf4cf66ffb4c62cb`

## 6) 剩余风险与下一轮建议
- 剩余风险：
  1. `check_api_layer_imports.py` 仍有存量 HTTPException detail 问题，默认仅告警；
  2. `--full` 测试覆盖与耗时需在真实发布窗口评估（当前仅验证 quick 门槛）；
  3. 目前未接入统一 CI workflow（本轮仅本地工程化增强）。
- 下一轮建议：
  1. 收敛 API 层异常为统一 envelope 后，将默认模式升级为 strict；
  2. 在 CI 增加 `pre_release_gate.sh --full --strict` 夜间任务；
  3. 对 skip 用例逐条梳理，区分“环境缺失”与“真实未实现”。
