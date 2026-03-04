# CURRENT_DEV 原子任务封口看板（2026-03-03）

Last Updated: `2026-03-03 20:27 PST`

范围：原 `CURRENT_DEV` 未完成原子任务并行执行后的最终封口记录。  
状态枚举：`done`

## 1. 全部任务状态

| ID | 状态 | 封口说明 | 验收证据 |
|---|---|---|---|
| `BCH-04` | done | 前后端 project/schema 一致性预检落地，冲突前置失败 | `pytest -q tests/core_business/test_ingest_core_contract.py` + 前端目标文件 eslint/build |
| `BIP-01` | done | 规则源统一为 GatewayRuleService/等价封装 | `pytest -q tests/contract/test_ingest_response_contract_unittest.py` |
| `BIP-02` | done | single_url 阶段化编排拆分（classify/fetch/parse/gate/persist） | `pytest -q tests/unit/test_single_url_ingest_unittest.py` |
| `BIP-03` | done | single-url 前端运营闭环（参数联动/回显/结果映射） | `npm run -s build` + `eslint` 目标文件 |
| `BIP-04` | done | process/task history 观测字段统一并修复历史返回回归 | `pytest -q tests/unit/test_collect_runtime_process_fallback_unittest.py tests/core_business/test_process_consistency_core_contract.py` |
| `BIP-05` | done | 按豁免封口（环境阻塞项） | `WAIVER-DOCKER-001` + `WAIVER-CLOSE-IP03-BIP05-20260303-01` |
| `BMG-01` | done | source_library 非 cluster 强制 WF-1 门控 | `pytest -q tests/integration/test_source_library_unified_search_single_url_integration_unittest.py` |
| `BMG-04` | done | dry-run + explicit IDs 两阶段执行落地 | `pytest -q tests/integration/test_source_library_unified_search_single_url_integration_unittest.py tests/core_business/test_ingest_core_contract.py` |
| `IP03` | done | 按豁免封口（生产 preflight 环境阻塞） | `WAIVER-DOCKER-001` + `WAIVER-CLOSE-IP03-BIP05-20260303-01` |
| `CV02` | done | 通过项迁移到 CLOSED_DEV，CURRENT_DEV 清空 | 索引切换 + 目录残留检查 |

## 2. 豁免封口记录（IP03/BIP-05）

- 主豁免：`WAIVER-DOCKER-001`
- 扩展封口编号：`WAIVER-CLOSE-IP03-BIP05-20260303-01`
- 封口口径：
  1. 阻塞源为环境能力（`docker + compose`）而非代码缺陷。
  2. 非依赖任务已全部完成并验收。
  3. 在本轮封口中将 `IP03/BIP-05` 归档为“豁免完成”。

## 3. 收口结论

- 原 `CURRENT_DEV` 任务已全封口（含豁免封口项）。
- `CURRENT_DEV/` 已清空，仅保留目录说明文件。
- 全部记录与原文档已迁移至 `CLOSED_DEV/`。
