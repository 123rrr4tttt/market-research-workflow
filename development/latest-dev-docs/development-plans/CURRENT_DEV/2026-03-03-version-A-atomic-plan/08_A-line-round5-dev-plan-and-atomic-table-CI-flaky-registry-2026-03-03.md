# A线第5轮：开发文档 + 原子任务表（CI Flaky Registry）

日期：2026-03-03

## 目标

在既有 flaky-observe 基础上补齐“台账治理”能力：
1) flaky 用例必须绑定 owner/issue/SLA/exit_criteria；
2) CI 自动校验并产出可读摘要；
3) 保持 observation lane 非阻塞。

## 原子任务表

| 任务ID | 任务 | 依赖 | 门禁 | 负责人 | 产物 |
|---|---|---|---|---|---|
| A5-T01 | 联网检索并沉淀知识池 | 无 | G0 来源可追溯 | research-owner | `信息源库/...round5.md` |
| A5-T02 | 设计 registry 数据结构（JSON） | T01 | G1 字段齐全 | qa-owner | `tests/quarantine/flaky_registry.json` |
| A5-T03 | 实现 registry 校验脚本 | T02 | G2 校验规则可执行 | ci-owner | `scripts/validate_flaky_registry.py` |
| A5-T04 | 补齐脚本单元测试 | T03 | G3 pytest通过 | test-owner | `tests/unit/test_validate_flaky_registry_unittest.py` |
| A5-T05 | 接入 GitHub Actions flaky-observe | T03 | G4 CI步骤可运行 | ci-owner | `.github/workflows/backend-tests.yml` |
| A5-T06 | 本地执行验证并留证 | T04,T05 | G5 命令可复现 | qa-owner | pytest + artifacts 结果 |
| A5-T07 | 封口文档与索引更新 | T06 | G6 文档可导航 | docs-owner | 09封口文档 + index/README |

## 门禁定义

- G0：至少3个外部来源，包含官方/行业实践。
- G1：registry 每条记录包含 `nodeid/owner/issue/sla_days/exit_criteria`。
- G2：脚本对缺字段、重复nodeid、非法SLA、非URL issue 报错。
- G3：新增单测通过。
- G4：workflow 产出 registry report + flaky report，并写入 job summary。
- G5：本地可执行命令跑通。
- G6：closing doc + index/README 更新完成。
