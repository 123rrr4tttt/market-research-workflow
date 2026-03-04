# 后端数据库标准化/向量化封口文档（2026-03-03）

## 1. 封口范围

- 数据库图真源主路径：`graph_db_*`（db-primary）口径统一。
- 向量化召回与分组：`node-similarity` / `node-merge-batch-suggest` / `node-merge-auto`。
- compare 项目全链路验证：建议、apply、回归。
- 中英节点归一增强：规则层字典 + LLM 字典补全 + 匹配评分 + 合并脚本。

## 2. 封口验收标准

- 主路径语义统一为数据库主路径（兼容历史字面量，不再作为主口径）。
- compare 项目完成全量去重/归一执行，demo 项目不受污染。
- 向量化与图标准化关键测试通过。
- 文档索引已更新到 `latest-dev-docs` 顶层与 `development-plans` 主入口。

## 3. 实际完成情况

### 3.1 数据库标准化

- 已完成配置与读写路径统一：`graph_db_*` 为主。
- 兼容层保留：历史 `graph_node_projection_*` 仍可读，但仅用于兼容期。
- 项目 schema 健康性已校验并修复尾部异常 compare 项（仅保留健康版本）。

### 3.2 向量化与融合链路

- 已通过批量建议与自动流程验证（召回->分组->建议）。
- compare 项目执行全量保守 apply（同类型 + 规范化同名）后，重复 display_name 组清零。

关键结果（compare: `demo_proj_compare_0303_121137`）：
- 全量去重执行后：`dup_display_groups: 32 -> 0`。
- 节点/边变化（阶段汇总后当前值）：`nodes=2690`，`edges=5859`。
- demo 对照项目保持不变：`demo_proj nodes=2772, edges=5917, dup_display_groups=32`。

### 3.3 中英归一自动化

- 已新增并接线能力：
  - `app/services/graph/bilingual_alias_dict.py`
  - `app/services/graph/bilingual_matcher.py`
  - `scripts/run_bilingual_dict_merge.py`
- 支持分批并发参数（避免长串串行）：
  - `--llm-workers`
  - `--llm-batch-size`
  - `--max-llm-nodes`
- 规则：先字典召回，再同类型匹配与阈值过滤，默认保守以防过融合。

## 4. 验证与回归

- 已执行关键回归：
  - `tests/unit/test_bilingual_matcher_unittest.py`
  - `tests/unit/test_graph_node_merge_llm_unittest.py`
  - `tests/contract/test_vectorization_contract_unittest.py`
  - `tests/integration/test_admin_graph_standardization_unittest.py`
- 结果：`24 passed`（2026-03-03 PST）。

## 5. 风险与边界

- 向量相似度仅用于召回，不能单独作为跨语种同义最终判定。
- 中英字典由 LLM 生成时，需阈值门控与同类型硬约束，避免过融合。
- apply 脚本已增加唯一约束冲突兜底（边/别名存在即跳过），避免整批回滚失败。

## 6. 结论

- 后端数据库标准化/向量化工作达到封口条件。
- compare 验证闭环完成，demo 基线未受影响。
- 文档与索引同步完成，可作为后续版本基线。

