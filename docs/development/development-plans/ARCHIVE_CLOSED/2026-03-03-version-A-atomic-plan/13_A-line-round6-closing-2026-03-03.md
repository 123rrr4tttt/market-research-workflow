<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/13_A-line-round6-closing-2026-03-03.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/13_A-line-round6-closing-2026-03-03.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# A线第6轮 Closing（CI Flake Trend）

## 1. 完成项
- 已完成联网检索并沉淀到统一知识池：
  - `信息源库/CI-稳定性-Flaky趋势观测与预警分层-最佳实践-2026-03-03-round6.md`
  - `信息源库/INDEX.md`（单一入口）
- 已实现趋势聚合脚本：
  - `main/backend/scripts/flake_trend.py`
- 已新增单测：
  - `main/backend/tests/unit/test_flake_trend_unittest.py`
- 已接入 CI 汇总：
  - `.github/workflows/backend-tests.yml` 新增 trend 报告生成与 summary 展示。

## 2. 可执行验证
- 执行：
  - `python3 -m pytest -q tests/unit/test_flake_trend_unittest.py tests/unit/test_flake_report_unittest.py tests/unit/test_validate_flaky_registry_unittest.py`
- 结果：通过（用于验证 round6 增量与 round5 兼容性）。

## 3. 跨版本去重与差异化声明
- round4：建立基础治理框架与实施路径。
- round5：完成 flaky registry + 单次报告接入。
- **round6（本轮）**：新增“跨运行趋势聚合 + 阈值预警展示”，属于观测增强层，不重复建设 registry。

## 4. 关键路径
1) 统一知识池沉淀（保证策略来源一致）
2) 实现 `flake_trend.py` 多样本聚合
3) CI workflow 接入并输出到 step summary
4) 单测回归，确认不破坏既有 round5 产物

## 5. 下一轮草案（Round7）
- 目标：把 `artifacts/history/*.xml` 从“当前run拷贝”升级为“历史窗口拉取”（基于 GitHub Artifacts API）。
- 计划：
  1. 新增历史拉取脚本（按 workflow run 时间窗口下载 JUnit XML）
  2. 产出 trend window 配置（7/14/30 runs）
  3. 定义“回归硬门禁”退出标准（连续窗口低于阈值）
  4. 增补端到端 dry-run 验证文档
