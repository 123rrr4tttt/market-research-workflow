# Version F 原子任务清单（LLM研究报告线）

分支：`feature/version-F-llm-report`

## Taskboard

- [x] F1 建立独立 worktree（`-F-llm-report`）
- [x] F2 联网检索并沉淀 LLM 报告生成最佳实践（模板/引用/门禁）
- [x] F3 设计结构化输出契约（topic/sections/sources）
- [x] F4 实现报告服务模块：`app/services/llm_report_generator.py`
- [x] F5 实现 API：`POST /api/v1/llm-report/generate`
- [x] F6 增加质量门禁计算：citation_coverage/source_count/unique_citations
- [x] F7 单元测试：`tests/unit/test_llm_report_generator_unittest.py`
- [x] F8 本地验证并记录结果
- [x] F9 更新文档索引与差异化声明

## 验收标准

1. 输入 topic + sources，返回 JSON 结构化报告。
2. 同时返回 Markdown 报告文本。
3. 返回 `quality_gate` 且可程序化判定 pass/fail。
4. 单元测试通过（Python 3.9 环境）。
