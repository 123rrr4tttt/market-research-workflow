# 后端文档

这里说明后端对象、领域边界、接口合同和主要执行链。总体设计见[架构导览与设计卷](../../../docs/architecture/README.md)，安装与认证见[使用说明](../../../docs/usage.md)。

## 核心架构

| 主题 | 入口 |
| --- | --- |
| 项目、来源、材料、检索、证据与写作的整体关系 | [架构导览与设计卷](../../../docs/architecture/README.md) |
| Agent、Cell、工具、批准和原生 Core | [Cell 现行接线](agent-cell-current.md) |
| 检索、专题调查、索引、知识和证据 | [普通搜索 API](../app/api/search.py)、[专题检索 API](../app/api/project_retrieval.py)、[类型化知识](../app/services/typed_knowledge) |
| 采集、解析、入库和任务 | [数据摄取](INGEST_ARCHITECTURE.md) |
| 来源库、通道与路由 | [来源库定义](RESOURCE_LIBRARY_DEFINITION.md) |
| API 响应、错误和兼容边界 | [API 合同](API_CONTRACT_STANDARD.md) |

## 领域专题

| 主题 | 入口 |
| --- | --- |
| 项目与数据 | [项目 API](../app/api/projects.py)、[实体定义](../app/models/entities.py)、[迁移](../migrations/versions) |
| 来源与配置 | [摄取来源](INGEST_DATA_SOURCES.md)、[资源池接口](RESOURCE_POOL_EXTRACTION_API.md)、[Reddit](REDDIT_API_SETUP.md)、[Reddit 限制](REDDIT_API_LIMITS.md)、[Twitter/X](TWITTER_API_SETUP.md) |
| 政策与可视化 | [政策 API](../app/api/policies.py)、[政策可视化数据口径](政策可视化数据校验与实时性说明.md) |
| 数据库与去重 | [实体定义](../app/models/entities.py)、[材料写入与去重](../app/services/discovery/store.py) |
| 日期与来源质量 | [日期提取与修复](日期提取与修复总览.md) |
| 社交图谱 | [图谱构建](../app/services/graph)、[管理 API](../app/api/admin.py)、[图谱设计原稿](../../../docs/architecture/information/social-graph.md) |
| API 路由与 OpenAPI | [路由入口](../app/api)；已启动服务的 `/docs` 提供当前 OpenAPI |
| 写作与报告 | [写作 API](../app/api/writing.py)、[报告 API](../app/api/llm_report.py) |
| 工作流与任务 | [工作流服务](../app/services/workflow_graph)、[任务接口](../app/api/process.py) |

接口响应以实际路由和客户端合同为准。开发命令见[开发指南](../../../docs/development/README.md)。
