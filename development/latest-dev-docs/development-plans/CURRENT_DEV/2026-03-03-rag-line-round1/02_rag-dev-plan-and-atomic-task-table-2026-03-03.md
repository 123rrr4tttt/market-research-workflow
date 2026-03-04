# RAG Line Round1 — Dev Plan + Atomic Task Table

## Goal
在不破坏现有A/B/C线的前提下，交付最小可运行 RAG 模块（索引->检索->重排->回答->评测）。

## Atomic Task Table

| ID | Task | Dependency | Output | Gate |
|---|---|---|---|---|
| D1 | 创建独立副本 `...-D-rag` 并切到 `feature/version-C-streamplus` | None | 独立开发空间 | 与A/B/C隔离 |
| D2 | 联网检索RAG最佳实践并沉淀文档 | D1 | 研究文档（01） | 有明确来源URL |
| D3 | 设计最小RAG模块接口与数据结构 | D2 | `minimal_rag.py` 初版 | 可独立运行 |
| D4 | 实现检索+回答链路（含rerank） | D3 | 可调用API | query->contexts->answer可输出 |
| D5 | 实现评测脚本（Recall@k、MRR） | D4 | `scripts/rag_eval.py` | 指标可计算 |
| D6 | 增加单元测试并执行验证 | D4,D5 | `test_minimal_rag_unittest.py` + 测试结果 | 关键断言通过 |
| D7 | 产出封口文档并更新索引 | D6 | closing doc + index update | 可追踪下一轮 |

## Execution Sequence
1. D1-D2（调研与沉淀）
2. D3-D4（最小链路实现）
3. D5-D6（评测与验证）
4. D7（收口）

## 差异化设计约束（新增全局约束已纳入）
- 本线只做 RAG 检索增强链路，不重复 ingest/gate/streamplus 的功能实现。
- 对其他线已存在能力采用“引用/对接”策略，不做二次实现。
- 交付门禁：目标、架构、关键模块、验证指标中至少两项与其他线不同（本线已满足四项）。

## Risks (Round1)
- 当前为轻量本地向量，非生产级embedding。
- 回答层是证据拼装，未接入LLM生成器与事实自校验。

## Next Round Upgrade Targets
- 替换为真实 embedding 模型（OpenAI/本地向量模型）。
- 接入 cross-encoder reranker。
- 增加 Ragas 指标流水线与回归基线。
