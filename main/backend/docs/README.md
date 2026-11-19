# 后端文档

这里说明后端对象、领域边界、接口合同和主要执行链。总体设计见[架构总览](../../../docs/architecture/README.md)，安装与认证见[使用说明](../../../docs/usage.md)。

## 核心架构

| 主题 | 入口 |
| --- | --- |
| 项目、来源、材料、检索、证据与写作的整体关系 | [架构总览](../../../docs/architecture/README.md) |
| Agent、Cell、工具、批准和原生 Core | [Agent、Cell 与原生 Core](AGENT_MACRO_ARCHITECTURE.md) |
| 检索、专题调查、索引、知识和证据 | [信息检索与知识组织](INFORMATION_RETRIEVAL_FRAMEWORK_DESIGN.md) |
| 采集、解析、入库和任务 | [数据摄取](INGEST_ARCHITECTURE.md)、[统一采集](UNIFIED_COLLECT_ARCHITECTURE.md) |
| 来源库、通道与路由 | [来源库定义](RESOURCE_LIBRARY_DEFINITION.md) |
| API 响应、错误和兼容边界 | [API 合同](API_CONTRACT_STANDARD.md) |

## 领域专题

| 主题 | 入口 |
| --- | --- |
| 项目与数据 | [项目 API](../app/api/projects.py)、[实体定义](../app/models/entities.py)、[迁移](../migrations/versions) |
| 来源与配置 | [摄取来源](INGEST_DATA_SOURCES.md)、[资源池接口](RESOURCE_POOL_EXTRACTION_API.md)、[Reddit](REDDIT_API_SETUP.md)、[Reddit 限制](REDDIT_API_LIMITS.md)、[Twitter/X](TWITTER_API_SETUP.md) |
| 政策与可视化 | [政策数据结构](政策数据结构说明.md)、[数据校验与实时性](政策可视化数据校验与实时性说明.md) |
| 数据库与去重 | [数据库结构](数据库说明文档.md)、[文档去重](文档去重逻辑说明.md)、[数据摄取内容](数据摄取内容.md) |
| 日期与来源质量 | [日期提取与修复](日期提取与修复总览.md) |
| 社交图谱 | [内容图谱 API](社交平台内容图谱API.md)、[生成标准](社交平台图谱生成标准文档.md) |
| API 路由与 OpenAPI | [路由入口](../app/api)；已启动服务的 `/docs` 提供当前 OpenAPI |
| 写作与报告 | [写作 API](../app/api/writing.py)、[报告 API](../app/api/llm_report.py) |
| 工作流与任务 | [工作流服务](../app/services/workflow_graph)、[任务接口](../app/api/process.py) |

接口响应以实际路由和客户端合同为准。开发命令见[开发指南](../../../docs/development/README.md)。
