# 香港水域调查：证据节点显示名修订记录

日期：2026-09-25

## 源数据修订

源目录：`/Users/wangyiliang/Desktop/科学/项目/05-案例、原型与验证/政治生态模型/香港水资源与水治理_信息搜集`。

本次在 56 个含证据的 `图.json` 中为全部 548 条 `证据` 记录补齐 `名称` 字段，并在 57 个 `图.json` 中为 57 条 `线索` 记录补齐展示名：

- 544 条使用同分册 `材料.tsv` 中该证据 `材料ID` 对应的 `标题`。
- 4 条证据的材料引用原本就是 `unresolved_reference`，未补造标题；使用其 `原文摘录` 前 48 个字符作为显示名，并保留未解析状态。
- 线索显示名使用对应现场名称，形如 `线索链：东江供水系统`，避免前端退回显示 `clue:01`。
- 轮次合并数据集 `资料/材料/_轮次/2026-09-19_01/图谱数据.json` 同步补齐 31 条证据显示名和 6 条线索显示名，SHA256 为 `fdaadef19334eea97484780037768f17271260540e4e89a8257ff89021dfc78b`。

原生 `校验图.py` 对 57 个 `图.json` 全部通过；`读图.py` 重新投影后仍观察到 496 个语义节点、366 条判断边、548 条证据、57 条线索。既有 170 条候选重复/候选缺 ID 警告保持原状，未为显示名改动研究事实。

## 框架与导入接口

Rapid 框架 `校验图.py` 与 `读图.py` 将 `证据.名称` 识别为可选展示字段，并保留线索额外展示字段。MRW retrieval profile 的 `evidence` 与 `clue` 类型新增可选 `name` 属性；导入时从源记录 `名称` 保留，导出时反投影回 `名称`，不改变 `证据ID`、`线索ID`、`边ID`、`材料ID`、端点或 observed revision。

## 数据库拓扑修订

通过正式 `POST /api/v1/information-topology/patches` 按当前 revision 更新状态：

- 53 个状态 revision 1 → 2。
- 3 个已有历史修订的状态 revision 2 → 3。
- 第一批共写入 548 个 evidence element replacement。
- 第二批为 57 个状态各写入 1 个 clue element replacement；最终 54 个状态 revision 为 3，3 个状态 revision 为 4。
- 所有稳定引用和端点不变，仅增加 `attributes.name`。

2026-09-25 按用户纠偏撤销 material 单独写入 `attributes.name` 的方案：第三批曾为 57 个状态的 325 个 material element 增加 `name`，随后用 325 个反向 replacement 移除该字段并保留 revision 历史。材料内容名回归 `material.title` 这一源权威，由统一内容名称 schema 在前端读取。

更新后 `GET /api/v1/information-topology/topologies` 读回：57 个当前状态、548 个 evidence 元素与 57 个 clue 元素均具有非空 `name`，缺失数为 0。示例：

| 证据 ID | 显示名 |
| --- | --- |
| `ev:依赖:环节:公共供水:行动者:广东省:1:item:2026-09-19:r1-001` | 香港政府新聞網 - 東江水供水新協議簽訂 |
| `ev:依赖:环节:公共供水:行动者:广东省:2:item:2026-09-19:r1-010` | 水務署2024/25年報 WSD Annual Report 2024/25 |
| `ev:管理:行动者:水务署:环节:公共供水:1:item:2026-09-19:r1-005` | WSD - Water & Sewage Tariff |
| `clue:01` | 线索链：东江供水系统 |
| `clue:624` | 线索链：香港港口 |

前端生产页 `#/visual/graph/policy` 已读回香港统一拓扑：3,938 个节点、2,432 条边、17 种节点类型，当前可见 141 / 215。GraphPage 的投影顺序是 `name` 优先，因此证据节点标题不再退回 `evidence · <证据ID>`。

## 验证

- 原生 `校验图.py`：57/57 通过。
- 原生 `读图.py`：548 条证据与 57 条线索均进入投影，样本 `名称` 读回正确。
- 后端聚焦测试：`tests/integration/test_information_topology_api.py::test_retrieval_import_api_resolves_project_semantics_before_topology_write` 与 `tests/integration/test_information_topology_retrieval_io.py`，9 passed，1 skipped。
- 拓扑接口读回：548/548 evidence、57/57 clue 有 `name`。
- 拓扑接口读回：325/325 material 均无 ad hoc `name`，321 个有非空 `title`，4 个为 unresolved 引用。

## 内容名称 Schema 与清单

源项目新增全局内容名称 schema 的绝对路径为：
`/Users/wangyiliang/Desktop/科学/项目/05-案例、原型与验证/政治生态模型/香港水资源与水治理_信息搜集/信息拓扑内容名称Schema.md`。

前端权威实现为 `main/frontend-modern/src/pages/graph/realizer/displaySchema.ts`：

- `node:*` → `name`
- `judgment` → `judgment`
- `evidence` → `name` → `original_excerpt`
- `clue` → `name`
- `material` → `title`；unresolved → `未解析材料引用`
- `attempt` → `result_note` → `actual_query`
- 其余 retrieval 类型按 schema 中的内容字段读取

所有类型禁止回退显示 `type_id · local_id`；无内容名时显示“未命名X”。

2026-09-25 晚间补充：该合同升级为跨模块结构性 overlay。所有新创建拓扑元素可使用 `content_name`、`content_summary`、`content_order`、`structural_role`、`source_uri`、`source_status`；后端 `profiles.validate_state` 统一校验这些字段，模块 profile 不需要重复声明。旧数据不迁移，读取时由模块字段派生结构性字段。

前端创建合同位于 `main/frontend-modern/src/features/information-topology/creationSchema.ts`，统一生成 `BoundRef`、结构字段与端点；报告大纲创建已改为该入口，并同时保留 profile 必需的 `title/order` 模块字段。后端派生合同位于 `main/backend/app/services/information_topology/structural_schema.py`。

## 投影顺序修复

图页原先在同一遍循环中先处理元素端点、再处理后续元素。当关系先引用 material 而 material 元素排在后面时，身份 map 会先落入一个空属性 material 节点，后续真实 `title` 被去重挡住，导致图页显示“未命名材料”。`topologyProjection.ts` 已改为两阶段：先物化所有元素和源属性，再生成端点关联边。源层 321/325 个 material 有标题，4 个为 unresolved，因此修复后正常 material 不应再显示“未命名材料”。

同目录生成 `材料节点清单.tsv`，包含当前 57 个 state 的全部 325 个 material element，字段为 `状态ID、材料ID、observed_revision、title、规范显示名、档、reference_status`。清单是派生审计产物，不是第二事实源。

材料审计结论：

- 57 个分册 `材料.tsv` 共 321 行正式材料记录，316 个唯一 `材料ID`。
- current topology 共 325 个 material element、320 个本地 `材料ID`；差额包含跨状态重复与 4 个 unresolved 引用。
- 5 个 `材料ID` 出现在多个状态；4 个标题一致，1 个标题不同：`item:2026-09-20:r3-03d-025`。两者保留为不同 observed bound references 的源标题，不在显示层擅自合并。
- 4 个 unresolved ID 为 `item:2026-09-19:r2-02d-c03`、`c07`、`c09`、`c11`；不补造标题、URL、档位或快照。
- Docker backend 重建后 healthy；前端页面实际加载香港统一拓扑。

## 数据管理统一读模型

HK 项目 `documents` 表为 0，而信息拓扑 current state 为 57、material 元素为 325，暴露出数据管理文档面只读取 `documents` 的结构缺口。`POST /admin/documents/list` 新增 `include_topology_materials` 可选参数；前端数据管理页启用该读模型。

统一列表规则：

- 普通 `Document` 行仍来自 `documents`，`source_kind=document`，保留原有提取/删除操作。
- 信息拓扑 material 作为只读投影列出，`source_kind=information_topology_material`、`readonly=true`，携带 `source_ref.topology_ref` 与 `source_ref.material_ref`。
- 拓扑材料显示 `title` 派生的内容名；unresolved 显示“未解析材料引用”。
- 拓扑材料不可选择、不可批量提取、不可删除，不写入 `documents` 表。

实际接口读回 HK 项目：`total=325`，第一页 10 条均为 topology material，标题如“香港政府新聞網 - 東江水供水新協議簽訂”。前端 `#/admin/ops` 实际表格已显示这些只读材料。
