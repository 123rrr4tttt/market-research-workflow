# 架构说明

MRW 用项目边界组织来源、文档、检索、图谱和报告。业务界面与 API 提供操作入口，领域服务拥有原始数据和写入，后台任务执行异步工作；Codex Core 使用平台开放的工具与能力。

## 模块关系

| 模块 | 责任与事实归属 |
| --- | --- |
| 项目与来源库 | 项目上下文、来源定义及采集参数；来源登记沿所属模块维护 |
| 采集与导入 | 获取材料、解析和记录来源；异步执行与失败归任务链 |
| 索引与检索 | 基于文档建立派生索引，按项目检索并记录实际结果 |
| 信息拓扑与图谱 | 表达实体、关系和版本引用；视图保留原模块的身份和 owner |
| 写作 | 组织大纲、引用和报告；正文由写作模块维护 |
| Agent | Codex Core 执行，Codex WebUI 交互；工具访问沿业务权限边界 |
| 任务与运维 | 队列、日志、worker 状态、健康和故障读回 |

原生能力在[贡献目录](../../contributions/project_catalog.py)接入，装配与投影复用既有规则。图谱、页面和索引是原始事实的表示，不能自行取得原模块写权限。

## 专题说明

| 主题 | 维护位置 |
| --- | --- |
| 信息检索与模块间关系 | [信息检索架构](../../main/backend/docs/INFORMATION_RETRIEVAL_FRAMEWORK_DESIGN.md) |
| Agent 与系统交互 | [Agent 架构](../../main/backend/docs/AGENT_MACRO_ARCHITECTURE.md) |
| 导入与摄取 | [摄取架构](../../main/backend/docs/INGEST_ARCHITECTURE.md) |
| 来源库语义 | [来源库定义](../../main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md) |
| API、错误与接口专题 | [后端文档](../../main/backend/docs/README.md) |
| 运行与隔离 | [运维说明](../../main/ops/README.md) |

专题中拟议结构与已实现行为按其状态说明区分。源码、测试和实际读回共同确定当前能力；旧计划编号只用于历史追溯。

## 历史架构资料

旧目录划分与迁移资料见[历史入口](../history/README.md)。既有文件与兼容链接保留，历史迁移清单为 [latest-dev-docs-entry-manifest.json](latest-dev-docs-entry-manifest.json) 和 [latest-dev-docs-content-plan.json](latest-dev-docs-content-plan.json)，由 [scripts/checkers/check_docs_root_content_plan.py](../../scripts/checkers/check_docs_root_content_plan.py)检查。
