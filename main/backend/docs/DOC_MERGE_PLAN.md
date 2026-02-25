# 文档合并与归档计划（已执行）

> 最后更新：2026-02 | 文档索引：`docs/README.md`

本文档记录 `main/backend/docs` 的后续合并计划。当前策略是先归档阶段性报告，再逐步合并重合主题。

## 已完成（本轮）

- 已新增 `docs/README.md` 作为文档索引。
- 已创建 `docs/archive/` 分主题归档目录。
- 已将明确为阶段性报告/测试结果的文档移动至 `archive/`。

## 执行结果（本轮已完成）

### 1. 日期提取专题（已完成）

已新增主文档：

- `日期提取与修复总览.md`

已整合来源（含归档）：

- `日期提取功能增强说明.md`
- `日期提取优化总结.md`
- `archive/date-extraction/发布日期提取分析报告.md`
- `archive/date-extraction/剩余文档日期提取分析报告.md`
- `archive/date-extraction/链接分析总结报告.md`
- `archive/date-extraction/修复脚本改进效果对比.md`

结果：

- 主文档保留当前能力、支持格式、流程与操作建议。
- 历史统计细节保留在 `archive/date-extraction/`。

### 2. 数据摄取/数据源专题（已完成）

已新增主文档：

- `INGEST_ARCHITECTURE.md`（合并流程图 + 深度分析）
- `INGEST_DATA_SOURCES.md`（合并数据源分析 + 发现总结）

已整合来源：

- `INGEST_FLOW_DIAGRAM.md`
- `INGEST_PIPELINE_ANALYSIS.md`
- `archive/ingest-research/DATA_SOURCES_ANALYSIS.md`
- `archive/ingest-research/DATA_SOURCES_FINDINGS.md`

已归档（历史过程）：

- `archive/ingest-research/SCRAPER_ADAPTER_IMPROVEMENTS.md`
- `archive/testing-reports/SCRAPER_TEST_RESULTS.md`
- `archive/testing-reports/发现功能测试报告.md`

### 3. 社交图谱规范专题（已完成）

保留两份主文档：

- `社交平台图谱生成标准文档.md`（架构/规范主文档）
- `社交平台内容图谱API.md`（接口使用主文档）

已处理：

- 将 `社交平台数据结构说明.md` 的关键结构内容并入 `社交平台图谱生成标准文档.md` 与 `社交平台内容图谱API.md`（摘要形式）。
- 已将 `社交平台数据结构说明.md` 移入 `archive/graph-specs/`。

### 4. 政策可视化校验专题（已完成）

已新增主文档：

- `政策可视化数据校验与实时性说明.md`

已整合来源：

- `archive/policy-visualization/政策统计一致性检查报告.md`
- `archive/policy-visualization/热力图数据实时性分析.md`

保留独立规范：

- `政策数据结构说明.md`

## 命名与结构规范（建议）

- 主干文档优先使用：`说明` / `规范` / `指南` / `总览`
- 阶段性材料使用：`报告` / `分析` / `测试结果` / `对比`
- 归档目录按主题分组，避免单层堆叠

## 后续维护建议（可选）

1. 增加“按角色阅读路径”（开发/运维/分析）。
2. 在主干文档中补充维护人和最近更新时间。
3. 对 archive 中长期不再使用的报告做二次压缩归类。
