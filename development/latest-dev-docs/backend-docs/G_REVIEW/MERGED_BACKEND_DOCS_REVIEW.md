# MERGED_BACKEND_DOCS_REVIEW

审查日期：2026-03-01（US/Pacific）  
审查范围：`development/latest-dev-docs/backend-docs`（仅该目录）

## 1. 总结结论

- 目录整体是 `main/backend/docs` 的镜像快照，文档主题完整，但存在明显“日期化快照文档”与“阶段性执行文档”堆积。
- 主要风险不是缺文档，而是**时效衰减**（尤其路由清单、外部平台配置、阶段任务板）。
- 建议将“主规范”与“阶段/证据文档”分层：主规范保留在索引主路径，阶段证据集中到独立归档分区。

## 2. 过时风险清单（按风险级别）

### 高风险（建议优先处理）

| 文件 | 风险类型 | 证据 | 建议 |
|---|---|---|---|
| `API_ROUTE_INVENTORY_2026-02-27.md` | 时间戳快照易过时 | 文件标题与正文明确 `Generated on 2026-02-27`，且路由面会持续变化 | 标记为“历史快照”，并在标题/首段增加“仅对应 2026-02-27 版本” |
| `FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md` | 迁移快照易过时 | 文件名含日期，依赖固定路由清单（135 条） | 迁移为“阶段记录”，核心契约收敛到统一 API 文档 |
| `PHASE2_VERIFICATION.md` | 环境路径和步骤可能失效 | 含绝对路径 `/Users/wangyiliang/projects/信息收集工作流/main/ops`，与当前仓库路径不一致 | 保留为历史验证记录，新增“当前环境请以 ops 实际路径为准” |
| `TWITTER_API_SETUP.md` | 第三方平台策略变化快 | 文中依赖 2023 年平台政策描述（套餐/权限可能已变化） | 增加“需以 developer.x.com 当日政策为准”的显式免责声明 |
| `REDDIT_API_SETUP.md` | 第三方访问策略变化快 | “无需 OAuth + 浏览器 UA”做法存在失效风险 | 补充“若返回 403/429 或策略变更需切 OAuth”的应急分支 |

### 中风险

| 文件 | 风险类型 | 证据 | 建议 |
|---|---|---|---|
| `README.md` | 导航链接失效 | `../API接口文档.md` 在本镜像不存在（实际位于 `../backend-core/API接口文档.md`）；`archive/*` 目录在本目录缺失 | 修正文档链接路径；对镜像缺失目录加“源目录可用、镜像未同步”说明 |
| `接口层调查文档.md` | 路由统计口径滞后 | 文中“90+ / 18 模块 / 行号定位”依赖静态扫描时点 | 在首段添加“以 OpenAPI/代码为准”的醒目标注 |
| `数据库说明文档.md` | 版本信息与生成时间老化 | 保留 `2025-11-02` 生成信息，后续 schema 变化会漂移 | 增加“最后校验版本”字段（按 commit/tag） |
| `政策数据结构说明.md` | 示例日期与版本标记老化 | 仍含 `2025-01-XX` 生成标记 | 将示例与规范部分拆分，示例单独标注“演示数据” |

### 低风险

| 文件 | 说明 |
|---|---|
| `INGEST_ARCHITECTURE.md`, `INGEST_DATA_SOURCES.md`, `RESOURCE_LIBRARY_DEFINITION.md` | 主体是概念/分层说明，时效性相对稳定 |

## 3. 重复主题（建议合并视图）

| 主题 | 涉及文件 | 重复点 | 建议主文档 |
|---|---|---|---|
| API 契约与路由 | `API_CONTRACT_STANDARD.md`, `API_ROUTE_INVENTORY_2026-02-27.md`, `接口层调查文档.md`, `FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md` | 契约、路由统计、接口约束多头描述 | `接口层调查文档.md`（结构）+ 单一 API 规范文档（契约） |
| 采集架构与执行计划 | `INGEST_ARCHITECTURE.md`, `UNIFIED_COLLECT_ARCHITECTURE.md`, `数据摄取内容.md`, `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md` | 架构目标、流程和任务清单交叉 | `INGEST_ARCHITECTURE.md`（架构）+ `RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md`（执行） |
| 图谱说明 | `社交平台图谱生成标准文档.md`, `社交平台内容图谱API.md`, `STRUCTURED_VS_GRAPH_ALIGNMENT.md` | 数据模型、API、对齐问题部分重复 | `社交平台图谱生成标准文档.md`（总规范） |
| 阶段性推进记录 | `INGEST_CHAIN_TASKBOARD_2026-03-01.md`, `INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`, `PHASE2_VERIFICATION.md`, `DOC_MERGE_PLAN.md` | 都属于阶段执行/证据材料 | 统一归入“阶段证据包”并从主索引弱化 |

## 4. 建议弃用文件清单（仅建议，不删除）

> 说明：以下为“建议弃用为主入口文档”，不是删除建议。建议保留历史副本并在首段标记 `Deprecated/Archived`。

1. `API_CONTRACT_STANDARD.md`  
原因：文件已自述“规范已并入 `../API接口文档.md` 第 0 节，此为独立副本”，存在双份规范漂移风险。

2. `API_ROUTE_INVENTORY_2026-02-27.md`  
原因：日期快照天然过时，且路由清单应由自动化脚本持续生成而非长期手工引用。

3. `FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`  
原因：面向特定迁移窗口，和路由快照强耦合，长期维护价值低。

4. `INGEST_CHAIN_TASKBOARD_2026-03-01.md`  
原因：任务板属性强、时间敏感，应归档为执行证据而非长期规范。

5. `INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`  
原因：证据矩阵是阶段交付物，不适合作为常态说明文档。

6. `PHASE2_VERIFICATION.md`  
原因：阶段验收步骤和本地绝对路径耦合，长期误导风险高。

7. `DOC_MERGE_PLAN.md`  
原因：文档已标注“已执行”，更适合作为历史变更记录。

8. `数据摄取内容.md`  
原因：当前内容是“任务清单草稿”（偏业务草案），与架构/实现文档边界不清。

## 5. 立即可执行的同步建议（不涉及删除）

1. 在上述建议弃用文件头部增加统一标签：`Status: archived (do not use as source of truth)`。
2. 在 `README.md` 增加“Source of Truth”区块，明确每个主题唯一主文档。
3. 修复 `README.md` 中当前镜像不可达链接：
   - `../API接口文档.md` -> `../backend-core/API接口文档.md`
   - `archive/*` 目录补充“仅源目录可用/镜像未同步”提示。
4. 对第三方平台文档（Reddit/Twitter）增加“最后外部政策核验日期”字段。

