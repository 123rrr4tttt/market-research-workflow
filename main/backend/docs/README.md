# 后端文档

全仓文档从 [统一导航](../../../docs/README.md) 进入；启动与认证见 [日常使用](../../../docs/usage.md)，当前系统边界见 [架构入口](../../../docs/architecture/README.md)。本目录保留后端专题说明，接口行为以当前路由实现和运行服务的 `/docs` 为准。

| 主题 | 文档 |
|---|---|
| API | [接口参考](../API接口文档.md)、[响应与错误规范](API_CONTRACT_STANDARD.md)、[接口分层](接口层调查文档.md) |
| 信息检索 | [语义、方法、结构与实现](INFORMATION_RETRIEVAL_FRAMEWORK_DESIGN.md) |
| Agent | [宏胞腔与 Codex Core](AGENT_MACRO_ARCHITECTURE.md)、[Codex WebUI](../../ops/codex-webui/README.md) |
| 数据摄取 | [摄取架构](INGEST_ARCHITECTURE.md)、[数据源说明](INGEST_DATA_SOURCES.md)、[去重逻辑](文档去重逻辑说明.md)、[日期提取](日期提取与修复总览.md) |
| 来源与资源库 | [资源库定义](RESOURCE_LIBRARY_DEFINITION.md)、[资源池提取接口](RESOURCE_POOL_EXTRACTION_API.md) |
| 数据与图谱 | [数据库说明](数据库说明文档.md)、[政策结构](政策数据结构说明.md)、[社交图谱标准](社交平台图谱生成标准文档.md)、[社交图谱 API](社交平台内容图谱API.md) |
| 来源配置 | [Reddit 配置](REDDIT_API_SETUP.md)、[Reddit 限制](REDDIT_API_LIMITS.md)、[Twitter/X 配置](TWITTER_API_SETUP.md) |

专题文档中的设计、实现计划和实测状态按其各自声明阅读。开发命令与现行规则统一见 [开发入口](../../../docs/development/README.md)；分发计划、阶段报告、旧路由盘点及本目录 `archive/` 的归属见 [历史资料](../../../docs/history/README.md)。
