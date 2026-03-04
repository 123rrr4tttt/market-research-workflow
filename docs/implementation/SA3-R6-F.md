# SA3-R6-F 执行记录

## 参考包消费与 repo-level 映射
- 已消费：`docs/reference-pool/latest-batch-2026-03-04.md`
- 映射确认：
  - 质量门禁实现：`main/backend/app/services/llm_report_generator.py`
  - must-check：`main/backend/scripts/check_llm_report_must_minset.py`
  - 单测：`main/backend/tests/unit/test_llm_report_generator_unittest.py`、`main/backend/tests/unit/test_llm_report_api_unittest.py`

## 最小实现
- 强化 must-check：在单测通过后，新增 quality gate 关键字段外显检查（gate_version/decision/hard_failures/soft_failures/missing_items/observability）。

## 验证
- 待执行并回填到本文件（见主回传）。

## 回滚点
- 待执行 `git rev-parse HEAD` 回填。

## 风险
- 低风险：仅增强门禁脚本，不改 API 合约。

## next-batch-trigger
- 若主控继续 R7：将 quality gate 指标导出到 CI artifact 或 dashboard。