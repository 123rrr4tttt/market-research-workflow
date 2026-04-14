# Version F（LLM研究报告线）最佳实践知识池（Round 1）

日期：2026-03-03 PST  
分支：`feature/version-F-llm-report`  
工作副本：`/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-F-llm-report`

## 1) 检索目标

围绕“输入主题 -> 输出结构化研究报告（Markdown/JSON）+ 可追溯来源 + 评审门禁”沉淀可复用规范。

## 2) 外部参考（可追溯）

1. Anthropic Docs - Prompt engineering overview  
   https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview
2. Anthropic Docs - Citations  
   https://docs.anthropic.com/en/docs/build-with-claude/citations
3. Anthropic Docs - Reduce hallucinations  
   https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-hallucinations
4. LangChain Docs - Structured output  
   https://python.langchain.com/docs/how_to/structured_output/
5. Ragas Docs - Faithfulness metric  
   https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
6. arXiv 2305.14627 - Enabling LLMs to Generate Text with Citations  
   https://arxiv.org/abs/2305.14627
7. Prompt Engineering Guide - Chain-of-Thought（用于结构化推理流程参考）  
   https://www.promptingguide.ai/techniques/cot

> 注：OpenAI 文档入口存在反爬校验（Just a moment），本轮以可稳定访问源优先。

## 3) 归纳出的实现基线

- 输出必须强制结构化（JSON schema first），Markdown 为渲染层。
- 引用必须以 source-id 显式绑定 section，避免“口头引用”。
- 报告生成与质量门禁解耦：先产出，再 gate（覆盖率、来源数量、唯一引用数）。
- 评审优先检查：
  - 引用覆盖率是否达标
  - 每条关键结论是否可回溯到 source-id
  - source 元数据是否完整（title/url/publisher/retrieved_at）

## 4) Version F 专属门禁定义（首版）

- `citation_coverage >= 0.8`
- `source_count >= 1`
- `unique_citations >= 1`

产物字段：`quality_gate = { citation_coverage, source_count, unique_citations, pass, rules }`

## 5) 去重策略

- 不重复实现已有 HTML/CSV 报表链路（`/reports`）；Version F 仅新增 LLM 结构化研究报告接口。
- 若未来需复用 ingest/discovery 结果，采用“引用既有模块输出”而非复制业务逻辑。
