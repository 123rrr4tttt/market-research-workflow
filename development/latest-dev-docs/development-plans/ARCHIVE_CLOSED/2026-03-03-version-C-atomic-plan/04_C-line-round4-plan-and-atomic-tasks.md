# C线第4轮：开发文档与原子任务表（基于知识池）

## 输入知识池
- `信息源库/global/research/2026-03-03-C-line-round4-best-practices.md`

## 目标
将 C 线 pre-release 能力从“单点脚本”升级为“分层流水线 + 结构化报告四件套 + 最小可观测检查”。

## 原子任务表（串行依赖 / 门禁 / 负责人 / 预期产物）

| ID | 原子任务 | 串行依赖 | 门禁 | 负责人 | 预期产物 |
|---|---|---|---|---|---|
| C4-T01 | 联网检索并沉淀最佳实践 | 无 | 来源>=4个官方/成熟站点 | subagent-C | `信息源库/global/research/2026-03-03-C-line-round4-best-practices.md` |
| C4-T02 | 设计 pre-release 分层流程（collect/check/report/publish） | T01 | 流程可落地到现有脚本 | subagent-C | `scripts/pre_release_pipeline.sh` |
| C4-T03 | 实现报告聚合器，生成质量/可观测/release notes | T02 | 生成四件套中后3件 | subagent-C | `scripts/pre_release_report_bundle.py` |
| C4-T04 | 接线最小门禁脚本输出 gate-result | T02 | `gate-result.json` 固定路径可产出 | subagent-C | pipeline 内对 `pre_release_min_gate.sh --report` 的调用 |
| C4-T05 | 添加自动化验证用例 | T03 | 单测通过 | subagent-C | `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py` |
| C4-T06 | 执行验证并产出证据 | T04,T05 | 脚本执行成功+测试通过 | subagent-C | artifacts + test logs |
| C4-T07 | 封口文档 + 索引/README 更新 | T06 | 封口字段完整 | subagent-C | `05_C-line-round4-closure.md` + index/README 更新 |

## 串行门禁说明
1. **先调研**（T01）后开发。
2. **先流程定义**（T02）后实现报告器（T03/T04）。
3. **先可运行**再补测试（T05），最后统一验证（T06）。
4. **验证通过后**才允许封口（T07）。
