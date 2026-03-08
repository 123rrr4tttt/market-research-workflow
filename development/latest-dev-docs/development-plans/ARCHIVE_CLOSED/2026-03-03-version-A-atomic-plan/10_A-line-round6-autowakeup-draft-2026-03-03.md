# A线第6轮自唤醒任务草案（待执行）

状态：READY（由A线第5轮自动生成）

## 目标

构建 flaky 趋势统计与轻告警层，形成“台账治理 -> 趋势治理 -> 升级门禁”闭环。

## 原子任务

1. A6-T01：检索 GitHub Actions artifacts 历史汇总最佳实践并沉淀知识池。
2. A6-T02：实现 `main/backend/scripts/flake_trend.py`（读取多个 junit xml，按nodeid聚合失败率）。
3. A6-T03：新增 `tests/unit/test_flake_trend_unittest.py`，覆盖聚合逻辑与阈值判断。
4. A6-T04：在 `flaky-observe` 增加趋势摘要输出（Top N + 超阈值标记）。
5. A6-T05：更新文档与封口，给出“何时把某flaky回归主门禁”的量化阈值建议。

## 门禁

- G0：来源>=3且可追溯。
- G1：脚本可在本地对样例数据执行成功。
- G2：新增单测通过。
- G3：CI summary 出现趋势段落。
- G4：封口文档含回滚路径。
