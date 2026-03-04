# SA3-R6-E 执行记录

## 参考包消费与 repo-level 映射
- 已消费：`docs/reference-pool/latest-batch-2026-03-04.md`
- 映射确认：
  - 配置：`main/backend/app/settings/config.py`
  - 深健康检查实现：`main/backend/app/main.py`
  - 集成验证：`main/backend/tests/integration/test_deep_health_db_degraded_unittest.py`

## 最小实现
- 新增 deep-health 连接池门禁参数：
  - `deep_health_pool_gate_enabled`
  - `deep_health_pool_exhaustion_ratio`
- 深健康逻辑改为按 ratio 计算触发阈值并在 details 外显：
  - `exhaustion_ratio`
  - `exhaustion_threshold`
- 新增集成测试覆盖 ratio 参数化场景。

## 验证
- 待执行并回填到本文件（见主回传）。

## 回滚点
- 待执行 `git rev-parse HEAD` 回填。

## 风险
- 低风险：默认 ratio=1.0 保持既有行为；仅扩展可配置能力。

## next-batch-trigger
- 若主控继续 R7：将 gate 参数接入环境模板与运行时指标面板。