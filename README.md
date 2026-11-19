# 市场研究工作流（MRW）

MRW 是一个运行在个人电脑上的**单用户市场研究工作台**。它以项目为边界，把来源采集、材料处理、检索与专题调查、信息结构、证据组织和写作放在同一套数据上；Codex 通过项目绑定的 Cell 调用工作台能力，执行结果仍由原业务服务和项目保存。

MRW 不要求自备服务器。[本机 Docker 部署](docs/usage.md#本机-docker-部署)与 [macOS 直装](docs/usage.md#首次运行)面向同一个工作台。两条安装路线都把 Codex WebUI 与 Cell 接到当前实例，而不是另开一套研究环境。

## 业务条线

下列界面链接使用 Docker 的默认本机端口；macOS 直装或自定义端口时，沿用相同的 `#/…` 路由并替换地址。

| 条线 | 业务范围 | 主要界面与实现入口 |
| --- | --- | --- |
| **项目与隔离** | 项目是资料、检索、文档、引用、Agent 会话和执行结果的范围；工作台窗口、在途任务和 Agent 线程固定各自项目。归档是业务写入的准入边界，不删除既有资料；恢复后可重新发起操作。跨项目复用的共享原文与项目内的研究结果分别归属。 | [项目与模板](http://127.0.0.1:15132/#/admin/projects)；[项目 API](main/backend/app/api/projects.py)、[项目上下文](main/backend/app/services/projects/context.py) |
| **来源、采集与材料** | 来源项说明采集对象，采集通道负责访问方式，运行时参数约束本次采集。文件、文本、URL 和外部来源进入后台解析、去重、入库和索引；材料保存、处理完成、可检索是不同状态。普通批量导入逐条提交，单条失败不吞掉其他成功项。 | [资源库](http://127.0.0.1:15132/#/admin/resources)、[采集](http://127.0.0.1:15132/#/workbench/ingest)、[特化采集](http://127.0.0.1:15132/#/workbench/ingest/specialized)、[原始数据处理](http://127.0.0.1:15132/#/workbench/raw-data)；[来源库定义](main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md)、[数据摄取架构](main/backend/docs/INGEST_ARCHITECTURE.md)、[统一采集](main/backend/docs/UNIFIED_COLLECT_ARCHITECTURE.md)、[采集 API](main/backend/app/api/ingest.py) |
| **检索、专题与信息结构** | 普通搜索用于查找项目已有材料，并标出命中版本和可用通道；专题检索是有可回看口径的研究运行，先预览检索方法，再由正式执行单元采集、抽取和判断证据。通道缺失不等于无命中，专题要求缺失通道时不能假装完整完成。信息拓扑保留材料在分析结构中的位置和关系，而不是另造一份正文。 | [资料与质量](http://127.0.0.1:15132/#/admin/ops) →「检索与历史」；[搜索 API](main/backend/app/api/search.py)、[专题检索 API](main/backend/app/api/project_retrieval.py)、[检索设计](docs/architecture/information/retrieval.md)、[信息拓扑设计](docs/architecture/information/topology.md) |
| **知识与证据** | 提取候选不因被提取就成为正式知识；按项目规则命中明确条件才可自动采纳，并保留来源、依据和撤回方式。模型提取必须由既有 Cell invocation 承载；没有该 invocation 时明确不可用，不直连 provider 冒充成功。引用固定使用时看到的材料版本，新版可以提示更新，不能静默改写已有引用卡和报告证据。 | [资源提取](http://127.0.0.1:15132/#/admin/resources/extract)、写作工作台的引用区；[类型化知识](main/backend/app/services/typed_knowledge)、[引用服务](main/backend/app/services/writing/citation_service.py) |
| **可视化与图谱** | 数据仪表盘汇总市场、社媒和政策资料；图谱把材料中的节点、关系和证据组织为可浏览结构。候选关系、搜索命中和图上的连线是不同的证据层级，图谱用于定位线索，不能替代原文和证据判断。 | [数据仪表盘](http://127.0.0.1:15132/#/visual/dashboard)、[市场](http://127.0.0.1:15132/#/visual/dashboard/market)、[舆情](http://127.0.0.1:15132/#/visual/dashboard/social)、[政策](http://127.0.0.1:15132/#/visual/policy)、[行业公司/商品/经营](http://127.0.0.1:15132/#/visual/catalog)；图谱入口见下表 |
| **分析与看板** | 从项目材料和图谱中查看分析视图、专题看板及状态汇总；这些视图是项目数据的投影，不等同于新增事实，也不替代底层材料与证据。 | [分析](http://127.0.0.1:15132/#/visual/analysis)、[看板](http://127.0.0.1:15132/#/visual/board)；[前端内核](main/frontend-modern/src/app/kernel)、[后端统计与报告接口](main/backend/app/api) |
| **写作与报告** | 写作工作台支持文档编辑、模板、引用卡、信息卡和 Markdown 导出；证据不足可以形成草稿，但正式报告须满足模板的证据要求。引用回到原文版本，资料缺失和取源失败分别说明。 | [写作工作台](http://127.0.0.1:15132/#/workbench/writing)；[写作 API](main/backend/app/api/writing.py)、[报告 API](main/backend/app/api/llm_report.py)、[写作界面](main/frontend-modern/src/pages/WritingWorkbenchPage.tsx) |
| **Agent、Cell 与工作流** | 从项目打开 Codex WebUI 后，新线程绑定该项目；Cell 把项目、线程、工具与审批带到具体调用。要求批准的操作在批准前不会由领域服务执行；批准后的效果由原领域服务写入，并从同一项目读回。工作流使用已定义图、运行参数和结果读回，可由 Agent 或获准入口发起。 | [Codex 工作台](http://127.0.0.1:15132/#/workbench/agent)、[胞腔视图](http://127.0.0.1:15132/#/workbench/cell)、[LLM 节点设计](http://127.0.0.1:15132/#/workbench/designer/llm)；[Agent 与 Cell](docs/architecture/agent/cell.md)、[当前接线](main/backend/docs/agent-cell-current.md)、[工作流服务](main/backend/app/services/workflow_graph) |
| **任务、管理与运行状态** | 后台任务的提交、执行、完成、失败和取消分别可读；任务回执不等于材料或报告已经完成。管理界面集中项目、来源、采集器、连接、模型模板和系统状态。 | [运行记录](http://127.0.0.1:15132/#/admin/process)、[进行中任务](http://127.0.0.1:15132/#/admin/process/processing)、[系统运行](http://127.0.0.1:15132/#/admin/backend)、[采集器](http://127.0.0.1:15132/#/admin/crawlers)、[连接设置](http://127.0.0.1:15132/#/admin/settings)、[模型与模板](http://127.0.0.1:15132/#/admin/settings/llm)、[业务指南](http://127.0.0.1:15132/#/admin/guide)；[任务接口](main/backend/app/api/process.py)、[业务链说明](main/frontend-modern/src/app/kernel/businessChainGuideData.ts) |

### 重要图谱

图谱页面使用同一套浏览、筛选、选择与详情交互，领域差异来自各投影的节点类型和关系。当前投影如下：

| 图谱 | 它回答什么问题 | 节点范围（实现定义） |
| --- | --- | --- |
| [**市场图谱**](http://127.0.0.1:15132/#/visual/graph/market) | 市场有哪些层级、参与者和市场数据线索，它们如何相连？ | `MarketData`、`State`、`Segment`、`Entity` |
| [**总图**](http://127.0.0.1:15132/#/visual/graph/deep) | 公司、产品、经营与市场线索怎样汇在同一张深图中？ | 市场、公司、产品、经营实体及 `TopicTag` 等全部深层实体 |
| [**公司图谱**](http://127.0.0.1:15132/#/visual/graph/company) | 公司由哪些主体、品牌、部门、伙伴和渠道构成？ | `MarketData`、`CompanyEntity`、`CompanyBrand`、`CompanyUnit`、`CompanyPartner`、`CompanyChannel` 及主题标签 |
| [**商品图谱**](http://127.0.0.1:15132/#/visual/graph/product) | 产品与型号、品类、品牌、组件、使用场景和主题怎样关联？ | `MarketData`、`ProductEntity`、`ProductModel`、`ProductCategory`、`ProductBrand`、`ProductComponent`、`ProductScenario` 及主题标签 |
| [**电商/经营图谱**](http://127.0.0.1:15132/#/visual/graph/operation) | 平台、店铺、渠道、指标、策略、地区和周期之间有什么经营关系？ | `MarketData`、`OperationEntity`、`OperationPlatform`、`OperationStore`、`OperationChannel`、`OperationMetric`、`OperationStrategy`、`OperationRegion`、`OperationPeriod` 及主题标签 |
| [**政策图谱**](http://127.0.0.1:15132/#/visual/graph/policy) | 政策、地区、政策类型、关键点和关联主体如何组织？ | `Policy`、`State`、`PolicyType`、`KeyPoint`、`Entity` |
| [**社媒图谱**](http://127.0.0.1:15132/#/visual/graph/social) | 帖子、关键词、人物、子版块、主题和情绪标签之间有什么联系？ | `Post`、`Keyword`、`Entity`、`Topic`、`SentimentTag`、`User`、`Subreddit` |
| [**新建图谱**](http://127.0.0.1:15132/#/visual/graph/builder) | 为尚未纳入固定投影的关系组织节点和连线模板。 | 模板构建入口；模板与可执行流程不是同一件事 |

实现入口：[图谱投影定义](main/frontend-modern/src/pages/graph/realizer/definitions.ts)、[图谱界面](main/frontend-modern/src/pages/GraphPage.tsx)、[后端图谱服务](main/backend/app/services/graph)。领域结构见[社交平台图谱设计](docs/architecture/information/social-graph.md)和[政策数据结构](main/backend/docs/政策数据结构说明.md)。信息拓扑与可视化图谱有不同用途，前者保留研究材料在分析结构中的出现和关系。

### 设计上的关键约束

- **项目不是标签。** 项目范围沿 API、后台任务、写作、Agent 会话和读回传播；Agent 线程绑定后不因窗口切换而改项目。
- **保存和可用不是一回事。** 材料入库、索引可查、引用可追溯、报告可导出分别验证。服务降级时保留成功通道结果并标明不完整。
- **候选与事实不是一回事。** 搜索命中、提取候选、图谱关系和正式证据各自有边界；模型建议不会自动变成已采纳知识。
- **代理不等于执行。** WebUI、Cell、API、worker 和领域 owner 各有职责；Cell 负责项目绑定和工具调用中继，不替代原领域服务的写入与判断。模型调用需要显式的 Cell invocation，后台临时脚本不是第二条中继。
- **失败和未知要可恢复。** 幂等只读操作可重试；副作用结果未知时先读回，仍无法确认就停止，不自动重放。归档停止新写入，但不伪造已接纳任务的取消。
- **状态面分别恢复。** 业务数据库、WebUI 线程存储、上传文件、搜索索引和在途任务不是一份状态；数据库恢复通过不等于完整恢复。

## 本机部署

完整安装包括业务界面、API、数据库、队列与检索，并能从业务界面进入**同一实例**的 Codex WebUI 和 Cell。默认只在本机使用，不需要部署到服务器。

| 安装方式 | 前置条件 | 默认入口 |
| --- | --- | --- |
| **Docker** | 能运行 Linux 容器的 Docker Engine、Compose 和可用的镜像及依赖下载网络；部署目标为 `linux/amd64`、`linux/arm64`。macOS、Linux 和使用 Linux 容器模式的 Windows 可按同一份 Compose 配置安装；平台支持以实际构建和验收为准。 | [安装、登录和验证](docs/usage.md#本机-docker-部署) · [业务界面](http://127.0.0.1:15132/) · [API 文档](http://127.0.0.1:18132/docs) |
| **macOS 直装** | 宿主 Python、Node.js、PostgreSQL（含 pgvector）、Redis、Elasticsearch 和 Codex。 | [首次运行](docs/usage.md#首次运行) · [WebUI 构建与启动](main/ops/codex-webui/README.md#mrw-本机构建与启动) · [业务界面](http://127.0.0.1:5173/) · [API 文档](http://127.0.0.1:8000/docs) |

Docker 方式从源码构建并启动服务；业务数据库、搜索索引、队列存储和 WebUI 各有独立的持久卷。Docker 中的 Codex 需在容器内授权，不借用宿主的登录状态。Windows 可直接用 [PowerShell 启动](docs/usage.md#windows-powershell)，无需额外安装 Bash。

安装验收不仅要看到页面和健康检查通过，还要确认材料经过后台处理后可搜索、项目绑定的 Codex 回合能经 Cell 读写本实例、需批准的写入在批准后才提交并可在业务界面读回，以及重启后资料和线程仍可访问。具体步骤见[安装验收](docs/usage.md#安装验收)。

## 文档导航

- **设计原稿：**[设计分册](docs/architecture/README.md)、[运行时合同](docs/architecture/runtime/contract.md)、[总体架构图集](docs/architecture/runtime/atlas.md)、[后端接口与领域文档](main/backend/docs/README.md)。分册保留原稿的定义、推导和图，不用 README 替代。
- **运行与开发：**[使用说明](docs/usage.md)、[运行、容器与恢复](main/ops/README.md)、[开发指南](docs/development/README.md)、[协作约定](AGENTS.md)、[Git 工作流](GIT_WORKFLOW.md)。
