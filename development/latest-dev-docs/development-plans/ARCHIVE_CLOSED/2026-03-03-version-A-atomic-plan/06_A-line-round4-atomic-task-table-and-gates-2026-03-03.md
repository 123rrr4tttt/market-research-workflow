# A线第4轮 原子任务表（并串行依赖/门禁/负责人/产物）

## 原子任务表

| 任务ID | 任务 | 并行组 | 串行依赖 | 门禁 | 负责人 | 预期产物 |
|---|---|---|---|---|---|---|
| A4-T01 | 外部最佳实践检索与摘要 | PG-R | 无 | G0 来源完整性 | research-owner | 知识池文档（含链接/边界/步骤/风险回滚） |
| A4-T02 | CURRENT_DEV 调研落盘 | PG-R | T01 | G1 文档可追溯 | docs-owner | round4 调研实施文档 |
| A4-T03 | CI workflow 主门禁稳定化改造 | PG-I | T02 | G2 YAML语法/策略一致性 | ci-owner | 更新后的 backend-tests.yml |
| A4-T04 | flaky 观察链路实现（脚本+报告） | PG-I | T03 | G3 报告可生成 | ci-owner | flake_report.py + artifact 产物定义 |
| A4-T05 | pytest marker 与 quarantine 规范 | PG-I | T03 | G3 marker 可识别 | test-owner | pytest.ini + quarantine README |
| A4-T06 | 单测补齐（报告脚本） | PG-I | T04 | G4 单测通过 | test-owner | test_flake_report_unittest.py |
| A4-T07 | 本地验证执行 | PG-V | T06 | G5 pass/skip/fail 记录 | qa-owner | pytest 执行证据 |
| A4-T08 | 封口文档 + 索引/README 更新 | PG-C | T07 | G6 可导航可回滚 | docs-owner | closing doc + index/README 更新 |

## 执行序列

1. G0-G1：先调研再落盘。
2. G2-G4：实施 workflow + 脚本 + 测试。
3. G5：执行本地验证并记录结果。
4. G6：生成封口文档并更新目录索引。
