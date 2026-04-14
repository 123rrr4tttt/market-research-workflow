# Version F 交付封口文档（LLM研究报告线）

## 交付范围

新增“研究报告生成模块”：输入主题与来源列表，输出结构化研究报告（JSON）+ Markdown 渲染 + 质量门禁结果。

## 代码变更

- `app/services/llm_report_generator.py`
  - `build_structured_report(...)`
  - `render_markdown(...)`
  - `evaluate_report_gate(...)`
  - `validate_report_structure(...)`
- `app/api/llm_report.py`
  - `POST /api/v1/llm-report/generate`
- `app/api/__init__.py`
  - 注册 `llm_report_router`
- `tests/unit/test_llm_report_generator_unittest.py`
- `tests/unit/test_llm_report_api_unittest.py`
- `scripts/check_llm_report_must_minset.py`

### 本轮增强（R4-F 补齐）

- 报告质量门禁：
  - 增加 `placeholder_content_detected` 硬失败判定，防止模板占位文本误通过。
  - 增加 `source_id_duplicate` 结构校验错误，强化引用可追溯唯一性。
- 模板稳定性：
  - 增加 `template_version` 并写入 JSON 与 Markdown。
  - 对 `section_titles` 做去空白、去重、长度截断与数量限制。
- 异常处理：
  - `start_job(...)` 纳入 `try`，避免前置异常造成作业状态丢失。
  - 未预期异常统一返回 `500 + LLM_REPORT_INTERNAL_ERROR`。
- 可观测性：
  - 增加 `gate_started_at/gate_finished_at/gate_duration_ms`。
  - 作业完成结果持久化完整 gate 关键字段（hard/soft/missing/rules/observability）。
- 安全：
  - Markdown 渲染对用户可控字段进行转义，降低注入/格式污染风险。

## 运行示例

请求：

```json
{
  "topic": "北美在线彩票增长",
  "sources": [
    {
      "id": "S1",
      "title": "Example Source",
      "url": "https://example.com/report",
      "publisher": "Example Org",
      "evidence": "market grew 12%"
    }
  ]
}
```

响应核心字段：

- `report`（结构化 JSON）
- `markdown`（Markdown 报告）
- `quality_gate`（门禁结果）

## 验证记录

执行：

```bash
cd main/backend
PYTHONPATH=. python3 -m pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py
PYTHONPATH=. python3 scripts/check_llm_report_must_minset.py
PYTHONPATH=. python3 -m compileall -q app/services/llm_report_generator.py app/api/llm_report.py app/api/__init__.py app/settings/config.py
PYTHONPATH=. python3 - <<'PY'
from app.services.llm_report_generator import build_structured_report, evaluate_report_gate, render_markdown

report = build_structured_report(
    topic='北美在线彩票增长',
    sources=[{'id':'S1','title':'Example','url':'https://example.com','publisher':'Org','evidence':'evidence'}],
)
gate = evaluate_report_gate(report)
md = render_markdown(report)
print(report.topic, len(report.sections), len(report.sources), report.template_version)
print(gate['decision'], gate['pass'], gate['hard_failures'], gate['soft_failures'])
print(md.splitlines()[0])
PY
```

结果：

- `pytest`: `11 passed, 9 skipped`
- `check_llm_report_must_minset.py`: `11 passed, 9 skipped`
- `compileall`: 退出码 `0`
- dry-run 输出：
  - `北美在线彩票增长 5 1 v1.1`
  - `pass True [] []`
  - `# 研究报告：北美在线彩票增长`

## 差异化声明（去重清单 + 独特点）

### 与 A/B/C/D/E/G 线去重清单

- 不复刻 ingestion gate 的规则引擎（B/C 线关注点）。
- 不复刻数据库 schema/迁移增强（E 线关注点）。
- 不复刻 crawler/source-library 管线（A/C/G 常见关注点）。
- 不重复已有 `/reports` HTML/CSV 导出逻辑，改为新增 LLM 结构化报告接口。

### Version F 独特点（满足“至少两项不同”）

1. **目标差异**：面向“研究报告编排与可追溯叙事生成”，而非数据采集或入库。
2. **架构差异**：采用 `schema-first JSON + markdown renderer` 双层产物架构。
3. **关键模块差异**：新增 `evaluate_report_gate`（引用覆盖率门禁）。
4. **验证指标差异**：以 `citation_coverage`、`unique_citations` 为主指标，而非吞吐/抓取成功率。

## 后续建议

- 将真实检索结果对接到 `sources` 输入（引用已实现采集链路产出，而非复制实现）。
- 将 `quality_gate.pass=false` 的报告接入评审队列，实现人工复核门禁。
