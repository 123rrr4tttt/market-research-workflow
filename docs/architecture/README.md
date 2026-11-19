# MRW 设计文档

MRW 在项目范围内把研究问题、外部来源和已有资料组织成可检索的材料、可复核的证据和可编辑的成果。读设计从下表挑选主题，不需要先了解项目的开发历史。

| 分册 | 完整设计稿 | 现行实现入口 |
| --- | --- | --- |
| **Agent 与 Cell** | [Agent 宏观架构：宏胞腔、双向中介与原生 Core](agent/cell.md) | [宿主接线与接口](../../main/backend/docs/agent-cell-current.md) |
| **来源、材料与采集** | [来源库定义](../../main/backend/docs/RESOURCE_LIBRARY_DEFINITION.md)、[数据摄取架构](../../main/backend/docs/INGEST_ARCHITECTURE.md)、[统一采集](../../main/backend/docs/UNIFIED_COLLECT_ARCHITECTURE.md) | [采集 API](../../main/backend/app/api/ingest.py)、[材料实体](../../main/backend/app/models/entities.py) |
| **信息结构与研究** | [信息检索架构](information/retrieval.md)、[信息拓扑设计](information/topology.md)、[社交平台图谱设计](information/social-graph.md)、[政策数据结构](../../main/backend/docs/政策数据结构说明.md) | [项目检索](../../main/backend/app/api/project_retrieval.py)、[信息拓扑](../../main/backend/app/api/information_topology.py)、[图谱接口](../../main/backend/app/api/admin.py) |
| **运行时与总体构造** | [函子化架构与运行时合同](runtime/contract.md)、[总体架构图集](runtime/atlas.md) | [原生贡献目录](../../contributions/project_catalog.py)、[运行时](../../main/backend/app/successor_runtime/runtime) |

设计稿保留定义、论证、图和例子。原稿中随附的实施计划和测试截面不作现行操作指南，也不证明已实现。安装与日常使用见[使用说明](../usage.md)，其他领域与接口入口见[后端文档](../../main/backend/docs/README.md)，部署和故障定位见[运维说明](../../main/ops/README.md)。
