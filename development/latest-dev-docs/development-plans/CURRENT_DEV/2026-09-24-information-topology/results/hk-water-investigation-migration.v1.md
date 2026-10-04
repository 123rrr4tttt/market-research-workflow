# 香港水域调查：Rapid 项目实例数据库迁移与同构读回

- 项目显示名：`香港水域调查`
- MRW `project_key`：`hk_water_investigation`
- PostgreSQL 数据库：本机 `postgres`
- tenant schema：`project_hk_water_investigation`
- 源域名：`香港水资源与水治理`，原样保留自 `域.json`；项目名与域词表名是两个身份
- 源目录：`/Users/wangyiliang/Desktop/科学/项目/05-案例、原型与验证/政治生态模型/香港水资源与水治理_信息搜集`
- 文件与状态摘要：[迁移清单](hk-water-investigation-source-manifest.v1.json)

## 已完成迁移

最初在本机 PostgreSQL 项目库中创建“香港水域调查”项目及独立 tenant schema。随后确认网页使用的是 Docker `ops-db`，而不是该本机实例；2026-09-24 已将项目行和 tenant 数据以追加方式同步到 `ops-db`。项目启用但未设为 active。未更改源项目目录。

57 个正式 `图.json` 分别成为 57 个当前 Rapid 拓扑状态；状态 ID 由相对源路径的 SHA256 派生，原始元素 ID 保持不变。当前 payload 共 3,994 个元素：判断边 366、证据 548、线索 57、节点 584、域词表快照 57、完整执行字段的检索 attempt 2,057，以及 4 个明确标记为 `unresolved_reference` 的材料占位引用。三个 provenance 补全状态各多一个历史 revision，因此共 60 行 revision、57 行 current。

关系、证据和线索端点保存在状态元素的稳定引用中；本次没有额外创建跨状态 link，所以 link 表为 0 行。Rapid 原生投影所需的 287 个结构文件（共 9,496,982 字节）作为只读 source provenance 存在数据库中，包括候选分面、候选表、报告与原始检索日志。没有把这些来源内容提升为正式证据或改写其 owner。

源 `检索记录.tsv` 有 2,557 行；其中 500 行缺少执行时间、工具或实际检索式，无法构成完整 attempt。这 500 行保留在原始 TSV provenance 中，没有补造执行信息。其余 2,057 条按命中、未命中、访问失败、偏题四种结果写为拓扑元素。

4 个证据材料目标在对应材料表中没有来源记录。数据库保留引用身份并标记为未解析，没有补造材料标题、URL 或档位。身份为：

- `item:2026-09-19:r2-02d-c03`
- `item:2026-09-19:r2-02d-c07`
- `item:2026-09-19:r2-02d-c09`
- `item:2026-09-19:r2-02d-c11`

项目源目录目前约 4,857 个文件、1,486,593,158 字节，其中 296 个 PDF 快照共 1,186,231,835 字节继续由原目录持有；数据库保留材料中的路径引用，没有将二进制快照塞进关系 payload。

项目 schema 初始化时，既有 bootstrap 因 tenant-only `search_path` 看不到 `public.vector` 而跳过了可选 `embeddings` 表；这不影响本次拓扑表、Rapid 数据读回或投影验收。若后续要在此项目启用向量嵌入写入，需要单独处理该扩展类型的 schema 可见性。

## Rapid 同构读回

从 PostgreSQL 导出并重建临时 Rapid 镜像目录后，逐文件比较 287 个结构文件：SHA256 和字节数全部与源文件一致。57 张图均通过 Rapid 原生 `validate_graph`。使用相同的 Rapid `信息结构.read_projection(root, all_rounds=True)` 分别读取原目录与数据库导出镜像；完整投影对象在只归一化绝对根目录字符串后完全相等。

两边观察计数相同：57 来源、316 材料、57 线索、496 节点、366 判断边、548 证据、0 逻辑依赖、757 候选、178 警告、0 冲突。线索顺序、重复位置以及 60 个 `断口:` 顺序项均包含在全量比较中；没有清理既有警告。候选 ID 按 Rapid 的轮次/分面身份由原生解析器处理，没有按重复的裸 ID 合并。

热身后 Rapid 投影的五次中位耗时为：源目录 78.70 ms，数据库导出镜像 85.87 ms。包含批量 PostgreSQL 读取、287 个文件重建和 Rapid 投影的三次端到端中位耗时约 447 ms。Rapid 读取阶段仍使用原生入口且耗时同一量级；数据库解码与重建产生额外约 0.37 秒。本轮没有发起网络搜索，因此没有新增检索 attempt 或研究事实；也没有据此宣称外网搜索吞吐与原生 Rapid 完全相同。

## 当前保证边界

这次验证证明了只读迁移观察范围内的关系保持：数据库导出的 source bundle 字节不变，Rapid 全轮投影经根路径归一化后不变。它没有证明 DB 编辑会自动回写原始 Rapid 文件、候选在编辑后的任意回投、报告正文通过报告 profile 编辑，或网络搜索端到端性能。报告与候选来源文件以 provenance 保留，写作、检索方法与快照的事实 owner 未转移。

信息拓扑相关定向测试为 `37 passed, 1 skipped`。跳过项是需要专用测试 URL/schema 的独立 PostgreSQL 集成测试；本次实际迁移使用了真实 PostgreSQL tenant schema，并已对 57 个状态逐条导出校验。

## 网页可见性记录（2026-09-24）

最初网页未显示项目和数据的直接原因是数据库目标不一致：迁移写入本机 PostgreSQL，而 `http://127.0.0.1:5174` 的前端通过 `ops-backend` 连接 Docker `ops-db`。截至本记录，`ops-db` 已包含 `hk_water_investigation` 项目行、独立 tenant schema、57 个当前状态及 60 行状态 revision；数据库迁移版本为 `20260924_000001`。`GET /api/v1/projects` 已返回“香港水域调查”，`x-project-key: hk_water_investigation` 下的拓扑 profile 接口返回 Rapid profile，直接读取一个状态返回 98 个元素。没有将项目设为 active。

为让网页加载当前工作树中的项目选择器和拓扑 API，本轮已重建 `frontend-modern` 镜像，并重建 `ops-backend`、`ops-frontend-modern` 容器；Compose 的 `PYTHONPATH` 已补入 `/app`，以便迁移脚本解析 `migrations.util`。本轮 Chrome 仍停在 `business_survey` 的图页，没有切换项目。

尚未闭合的可见性缺口：当前图页的旧图数据源不读取 `retrieval/rapid` 状态；抽象拓扑 API 可以按已知状态身份读取单个状态，但网页没有通用的状态目录/浏览入口。因此“项目已进入网页项目列表”和“迁入的 57 张 Rapid 图已在网页中可浏览”是两项不同结果：前者已验证，后者未实现。本记录只登记该缺口；本轮未继续扩展 API 或 UI 来强行补齐。

## 图页验证观察（2026-09-24）

图谱 realizer 接口整理期间，`tests/e2e/graphpage.spec.ts` 的 8 项通过，包含新增的总图多标签投影切换与 3D 画布重挂载检查，覆盖 2D/3D 切换、force3d scene、快速引擎切换/降级及原图构建器路径。独立运行 `check:graph-runtime-pixel-gate` 时，测试在进入像素/画布断言前未找到 `市场图谱` 一级标题（`getByRole('heading', { level: 1, name: '市场图谱', exact: true })`，5 秒超时）。该项仍记为未解释的前端可见性/测试前置问题；未据此改动页面、路由或测试，也不能把它解释为 3D 像素验证通过或失败。

## Docker 前端重建与图页只读验证（2026-09-24）

按当前运行实例 `ops` 重建 `frontend-modern`：`docker compose -f main/ops/docker-compose.yml --profile modern-ui build frontend-modern` 成功，镜像 manifest digest 为 `sha256:0b5aecb6fd24965ce3c8593cc623c0c8cc4374b2ad5fbffeda399d292e6d2d4`。随后仅执行 `up -d --no-deps frontend-modern`，`ops-frontend-modern-1` 已重建并运行；backend、db 和迁移数据均未重启或修改。`http://127.0.0.1:5174/`、`/#/visual/graph/market` 均返回 HTTP 200，Docker backend health 为 `ok`。

针对容器实际页面的 Playwright 只读检查无 page error；市场视图的 5 个投影标签可见，切换到“公司图谱”后标签选中态正确，3D 模式入口仍可见，拓扑面板没有创建、保存或同步按钮。未切换活动项目，未触发任何拓扑写接口。

同时确认网页项目选择列表可见 `hk_water_investigation`，但该项目的当前旧图数据请求 `GET /api/v1/admin/market-graph?view=market_deep_entities&limit=100&project_key=hk_water_investigation` 返回 HTTP 200 且 `nodes=[]`、`edges=[]`；`project-customization/graph-config` 响应体的 `data.project_key` 为 `default`。抽象拓扑页针对 `graphPage:company` 的只读请求返回 `NOT_FOUND`，符合该视图尚未保存图页拓扑状态的事实。此次观察与上文所记的已知缺口一致：旧市场图 API 未从 Rapid 迁入的 57 个状态构造页面图，因此 Docker 重建验证了最新前端已送达和交互可用，但未使迁入图数据出现在图页。该缺口只作记录，未改 API、数据库、项目选择或图谱数据。

## 通用项目语义绑定的香港案例实跑（只读）

2026-09-24 在实际 Docker `ops-backend` 容器中，通过其现有 `DATABASE_URL` 对 `ops-db` 的 `project_hk_water_investigation.information_topology_states` 执行只读查询。每个当前状态均从其持久化 `domain_vocabulary` 快照重建项目语义值和精确 `BoundRef`，调用通用 `resolve_project_semantics` 按原 `profile_id` / `profile_version` 解析 profile，再用该 profile 校验对应拓扑状态。

结果：57/57 当前状态绑定与结构校验通过，共校验 3,994 个元素，profile/version 身份匹配，0 失败。此次执行没有创建、更新或删除数据库行，也没有重启服务；它证明通用语义绑定能够承载香港项目已有 Rapid 语义快照并保持统一拓扑的结构校验。网页图页仍未从这些状态生成图形投影，旧图 API 的空节点/边观察不变。

## 项目级统一图谱投影接入（2026-09-24）

57 个来源分册继续只是 agent 消费粒度；图页不会把它们显示成 57 张独立图。新增只读 `GET /api/v1/information-topology/topologies`，在一个项目作用域查询中返回当前拓扑读模型，再由 GraphPage realizer 选择项目绑定的 `retrieval.domain.*` 语义投影并统一合并。元素身份按完整 `BoundRef`（项目、模块、命名空间、类型、本地 ID、观察修订与内容摘要）去重。拓扑元素保留为节点，端点角色投影为有向关联边；因此多端点线索、证据、判断与 attempt 等不同结构不会被强行压成一种固定关系。无该项目语义绑定的项目仍沿用既有市场/政策/社媒图 API。

香港项目实跑：单次只读接口返回 57 个当前状态、3,994 个拓扑元素；投影后因跨册共享的 bound vocabulary 身份合并为 3,938 个节点，保留 2,432 条端点关联边、41 种节点类型。容器网页图页显示非空网络，原 2D 控件、力学参数面板及 3D 模式入口均保留；切换 `react-force-graph-3d` 后观察到节点簇实际渲染。项目状态与拓扑数据未被修改。Docker 后端与前端已恢复运行，`/api/v1/health` 与 `http://127.0.0.1:5174/` 返回 200。

本次前端生产构建、TypeScript 检查通过；GraphPage force3d contract 与 i18n slice 检查通过；`tests/integration/test_information_topology_api.py` 为 11 passed。浏览器的香港真实案例已确认 2D 与 force-3D 画面非空。隔离 Playwright 环境的图页套件未作为本次验收：其应用壳健康、配置、项目和 Codex auth 请求使用 fail-closed 代理，旧路由测试在进入图页前已因缺少一级标题失败，故不计作本次实现的通过证据。

## 材料 URL 回填与前端可见性（2026-09-26）

用户指出“hk 原本的数据集是有 url 的”。核对结论：源项目确实保存 URL，此前的缺口来自迁移只读取了 `材料.tsv` 的旧表头，而多数分册的 `材料.tsv` 没有 URL 列。URL 实际分布在同轮次的 `候选材料总表.tsv`、`候选.tsv`、`快照审计.tsv` 以及轮次级 `URL审计.tsv`；`材料节点清单.tsv` 只承载显示名。

源侧回填规则（不补造，全部按源记录联结）：

1. 以 `候选ID` / `材料ID` 联结 `候选材料总表.tsv`、`候选.tsv`；
2. 以 `快照相对路径` 的 basename 联结 `快照审计.tsv`、`URL审计.tsv`；
3. 以规范化 `标题` 联结同轮次候选行；
4. 标题内嵌形如 `……｜https://…` 的 URL 按原文取出。

结果：57 个 `材料.tsv` 中 52 个新增 `URL` 列；316 条正式材料记录中 306 条解析到 URL。剩余 10 条在源 `URL审计.tsv` 中本身记为“无URL”（1 条派生 TSV、2 条 cap102 目录存档、4 条页面/数据集页、3 条 403/406/404 错误页）；4 条原本就是 `unresolved_reference` 占位。两类都不补造。

数据库侧：通过正式 `POST /api/v1/information-topology/patches` 批量 replace，52 个状态共 292 条 material 元素写入 `attributes.url`，源 `observed_revision` 与端点保持不变；19 条原本已有 URL。回读 `GET /api/v1/information-topology/topologies` 得到 325 个 material 元素中 311 条带 URL（此前 19 条），14 条为上述无 URL / 未解析项。

读模型与前端：`POST /api/v1/admin/documents/list`（`include_topology_materials=true`）的 `Document` 行补出 `uri` 字段，与拓扑 material 投影的 `uri` 语义一致；运维页文档表新增“来源 URL”列，只读 material 行渲染为外链。实跑证据：容器页面 `#/admin/ops`（`market_project_key=hk_water_investigation`）首屏 20 行全部渲染可点击 URL，无 page error；后端 `/admin/stats`、`/dashboard/stats` 在该项目下 `documents.total=325`。

本轮同时修复一项由该读模型引入的回归：`project_default` 缺少 `information_topology_states`（该 tenant schema 早于拓扑表登记），`/admin/stats`、`/admin/documents/list` 对其返回 `UPSTREAM_ERROR: UndefinedTable`，并留下 `idle in transaction` 连接。按项目既有 `ensure_project_schema_ready('default')` 补齐缺失表后，`default`、`business_survey`、`demo_proj`、`hk_water_investigation` 四项目的 `/admin/stats` 均返回 `ok`。未改设施协议，未改其他项目数据。

仍未接通的部分：拓扑 material 目前是只读投影（`readonly: true`、字符串 ID），没有对应 `Document` 行，运维页的“文档重提取/专题提取”对它们不可用；`hk_water_investigation` 的 `documents` 表为 0 行、Elasticsearch 无索引、后端容器也未挂载 HK 源目录，因此内容阅读、正文抓取、索引与检索链尚未贯通。下一步需要项目绑定层的 material → Document 桥：按 material 的 `url` 走抓取、按 `snapshot_path` 走受管导入，写入 `Document` 时保留 `source_ref` 回指拓扑 `BoundRef`，再复用既有 raw-import/抽取/索引/检索链。

## 领域关系语义的读取模型机制（2026-09-26）

图谱页此前只出现三种边类型，原因是 realizer 按“承载端点的元素类型”分组（judgment／evidence／clue），而 Rapid 数据里的领域关系名（22 种声明、21 种在用）存在于判断元素的 `edge_type`，从未进入投影。本轮不针对香港写特例，而是把“项目声明一次、读取模型派生、读者只消费”的机制补齐：

1. **单一作者声明位置**：模块 profile 的 `TypeRule` 新增 `relation_token_attribute`，声明该类型用哪个作者字段承载领域关系名。校验要求该字段必须是本类型已声明的属性。检索模块只在 `judgment` 上声明 `edge_type`；`evidence` 的 `effect`（支持／限定）是证据立场而非关系名，因此不声明，回落原行为。
2. **派生读模型**：`structural_schema.derive_read_model_attributes` 把声明字段投影为结构性只读字段 `relation_token`，与既有 `content_name`／`source_uri` 同族。它只出现在 `GET /information-topology/topologies` 的读取模型中，不进入持久化 payload，也不是可创作字段，因此不构成第二事实源。
3. **前端只消费**：realizer 把 `attributes.relation_token` 透传为边的 `relation_token`，边的元素类型仍保留在 `relation_class`（形状族与回溯不变）。
4. **图例分级**：`EdgeLegendTier` 新增 `domain`（页面文案“项目关系”），优先于 `class`／`pred`／`type`。没有声明关系名的项目完全回落原三级行为。
5. **样式绑定轴**：项目自定义 `graph_edge_style_bindings` 新增 `byRelationToken`，与 `byRelationClass`／`byPredicate`／`byType` 同层，项目可按关系名绑定图例库中的形状（曲直虚实、箭头符号）。

香港实跑（只读回读）：57 个状态共 3,994 个元素中 366 个 judgment 带派生关系名，去重 21 种；图谱页边图例出现两层，`项目关系` 21 项（管理 96／表达 80／组织 72／判断 64／中介 50／依赖 44／再生产 40／分配 38／转移 38／调和 36／赋能 32／支配 32／组成 32／爆发 18／上收 16／正当化 16／介入 8／占有 8／剩余流向 6／传播 4／统治 2，计数为端点关联边数），`关系大类` 仍为证据 1096、线索 604。页面无 page error。

验证：`tests/unit/test_information_topology_retrieval.py` 新增两条（声明投影、声明必须指向已声明属性），与 core／project-bindings／report-method／native-adapters 合计 31 passed；`tsc -b`、相关 ESLint、graph i18n slice（391 keys）、force3d frontend contract、topology platform contract 通过；`resolve_graph_edge_style_bindings` 的 `byRelationToken` 轴在运行容器内实读确认。

边界：默认视觉仍按形状族分派（判断关系的 21 项共用“双线·实线”），项目要用更丰富的区分需显式写 `byRelationToken`。若希望默认即按关系名分散形状，需要一个作者化的顺序来源（例如域词表 `edge_types` 的声明顺序）作依据，本轮未引入该默许映射。

## 边样式设施：完整组合空间与项目声明顺序的默认分派（2026-09-26）

用户指出“线的类型、形状、直曲、虚实应该挺多的”。此前目录只有 16 个手写样式，且判断关系的 21 个关系名默认共用同一形状。本轮把样式目录改成“设施级完整空间 + 项目声明顺序驱动默认分派”，仍不写香港特例：

1. **完整组合空间**：目录由 `EDGE_STROKE_KINDS`（直线／曲线／波浪线／双线）× `EDGE_LINE_TYPES`（实线／虚线／点线／长虚线／点划线）× `EDGE_SYMBOL_SETS`（箭头／圆圈箭头／双圆圈／圆圈三角／三角／菱形／无符号）生成 140 个网格样式（id 形如 `curved-dashed-arrow`），加回 16 个既有具名预设，共 156 项。曲直与虚实各自是声明轴，`curveness` 也随类型（曲线 ±0.2／−0.18，双线 0／0.12）。既有预设 id 保留，项目旧绑定不受影响。
2. **默认分派来源**：项目在域词表里以作者顺序声明 `edge_types`，图页投影把这串顺序带出为 `relation_vocabulary`；`defaultRelationTokenBinding` 按该顺序沿“直曲 × 虚实”对角线取样式，前 20 个关系名互不重复，其后按符号集轮转。因此项目声明多少关系名，就得到多少互不相同的默认线型，而顺序由项目自己确定，不是前端随意指派。
3. **绑定优先级**：`mergeEdgeStyleBindings(派生, 拓扑绑定, 项目配置绑定)`，显式绑定始终覆盖派生默认；`byRelationToken` 仍是项目可写的样式轴。
4. **消费端不变**：2D（ECharts）与 3D（force graph）都只读 `graphEdgeProfile` 的 `strokeKind`/`lineType`/`curveness`/`symbol`，因此新格子自动可渲染；图例徽章 `EdgeLegendBadge` 同样按这四项绘制。

香港实跑：图例 `项目关系` 21 项的样式标签去重 19 个（21 项对应 21 个不同样式 id，其中两项与另两项同为“曲线·点线”“直线·实线”但符号集不同，标签只显示直曲·虚实）。示例：管理·曲线·点线、表达·直线·虚线、组织·直线·点线、判断·曲线·长虚线、中介·曲线·虚线、依赖·直线·点划线、再生产·双线·长虚线、分配·波浪·虚线、转移·直线·实线、调和·双线·点线、支配·波浪·点划线、统治·双线·虚线；页面无 page error，2D 画布正常渲染曲直与虚实。图例截图见 `hk-edge-legend-2026-09-26.png`。

验证：`tsc -b`、相关 ESLint、graph i18n slice（391 keys）、force3d frontend contract、topology platform contract 通过；样式空间用构建产物直接运行核对（目录 156 项、网格 140 项、分派顺序 140 项唯一、21 个关系名→21 个不同样式 id、显式绑定覆盖派生默认）。前端镜像已重建。

边界：默认分派只作用于声明了 `relation_vocabulary` 的项目绑定拓扑；市场／政策／社媒等旧图数据无 `relation_token`，行为不变。

## 关系不再成为节点：结构角色与关系轴（2026-09-26）

用户指出“有些边的类型也变成节点了”，并举例证据其实是证明关系、真正的节点是材料。此前 realizer 把每个拓扑元素都物化成节点、再把端点物化成关联边，所以 `judgment`（判断边）与 `evidence`（证明关系）同时以节点和边的形态出现。本轮把“元素／关系”的角色判定放回模块声明，不写类型特例：

1. **声明**：`TypeRule` 新增 `structural_role` 与 `relation_axis`。`structural_role="relation"` 表示该类型是关系；`relation_axis` 以“源角色 → 目标角色”命名两个端点角色，校验要求角色已在该类型的端点声明中、两角色互不相同，且必须与 relation 角色同时出现。
2. **派生**：读取模型在元素未自述 `structural_role` 时填入声明值，并在角色为 relation 时派生只读字段 `relation_axis`；作者自述的结构角色优先（报告大纲的 `member` 不受影响）。派生字段仍只存在于 `GET /information-topology/topologies` 读取模型。
3. **声明内容（retrieval）**：`judgment` = relation，轴 `from → to`；`evidence` = relation，轴 `material → judgment`；`logical_dependency` = relation，轴 `before → after`。`material`、`node:*`、`clue`、`candidate`、`attempt`、`domain_vocabulary` 等仍为元素。
4. **realizer**：关系元素不再成为节点，而是按轴物化为**一条**有向边（`type: topology_relation`，保留 `relation_class`、`relation_token` 与完整 `topology_attributes`）；元素元素保留原有端点关联边。当元素端点指向一个关系（例如线索的 item 指向判断边或证据）时，解析会沿该关系的轴目标继续（深度上限 4），因此不会隐式生成关系节点。

香港实跑：读取模型回读 `judgment` 366、`evidence` 548 带角色与轴，非关系元素 3,080 个（15 种）。图页节点类型从 11 种降为 10 种（`material`、`node:行动者`、`node:阶级机体`、`node:制度安排`、`node:社会关系`、`node:环节`、`node:意识形式`、`node:生活实践`、`node:技术物`、`clue`），`judgment` 与 `evidence` 不再出现在节点图例；边图例为 `项目关系` 21 项（管理 48／表达 40／组织 36／判断 32／中介 25／依赖 22…，计数回归“每判断边一条”）、`关系大类` 证据 548 与线索 604。页面无 page error，2D 与 3D 均可渲染。

验证：后端单元 33 passed（新增关系角色／轴声明与派生两条，含轴角色未声明、轴缺少 relation 角色两类拒绝）；`tsc -b`、相关 ESLint、graph i18n slice（391 keys）、force3d contract 通过；容器内拓扑读回与真实浏览器核对；前端镜像已重建。

边界：`attempt`（2,057 条检索尝试）仍是元素节点，因为它是模块声明的检索执行记录而非关系；若要把这类过程记录也排除出图页，只需在同一处声明其他角色并让 realizer 忽略该角色，本轮未扩大范围。

## 非信息类元素退出图页：annotation 角色（2026-09-26）

用户指出“有些非信息类的东西就不要加进去了，这个图谱是用来刻画事件的”。上一轮遗留的 `attempt` 之外，图页还以节点形式呈现了 `domain_vocabulary`（域词表快照）与 `clue`（线索链，即检索线程），节点图例里表现为“方法”一组。本轮把“这类记录不进图”也变成模块声明：

1. **角色词表**：结构角色沿用既有 vocabulary `member / relation / root / annotation`。`annotation` 表示“记录检索过程或登记信息、不是被研究的事件内容”，realizer 既不建节点也不建边，元素仍完整保留在拓扑读取模型中。
2. **声明内容（retrieval）**：`attempt`（检索执行记录）、`keyword_plan`（关键词计划）、`source_route`（来源路线计划）、`source_registry`（来源登记）、`domain_vocabulary`（域词表快照）、`clue`（线索链线程）、`report_source_binding`（报告来源绑定）标记为 `annotation`；`candidate`（候选材料）、`gap`（研究缺口）仍是内容元素；`judgment`／`evidence`／`logical_dependency` 仍是关系。理由：前者是 agent 的执行与登记层，后者是关于研究对象的内容或分析。
3. **realizer**：annotation 元素在节点物化与边生成两处都被跳过；若某个元素的端点指向 annotation 目标（例如依赖关系指向线索），解析返回空并跳过该边，不隐式生成节点。

香港实跑：读取模型回读确认 annotation 2,171 个（attempt 2,057、clue 57、domain_vocabulary 57）、relation 914 个（judgment 366、evidence 548）。图页节点类型收敛为 12 种——`material` 325 与 11 类 `node:*`（行动者 167、制度安排 122、现场 57、环节 47、意识形式 41、技术物 41、社会关系 31、生活实践 27、货币流 24、阶级机体 24、剩余 3）；边为 `项目关系` 21 项（管理 48／表达 40／组织 36／判断 32／中介 25／依赖 22／再生产 20／分配 19／转移 19／调和 18／赋能 16／支配 16／组成 16／爆发 9／上收 8／正当化 8／介入 4／占有 4／剩余流向 3／传播 2）与 `关系大类` 证据 548。节点图例的“方法”组消失，页面不再出现 `clue`／`evidence`／`judgment`／`attempt` 字样；无 page error，2D 与 3D 均可渲染，Chain 面板仍可用。截图见 `hk-event-graph-2026-09-26.png`。

验证：后端单元 34 passed（新增 annotation 声明与派生一条，并断言 `material`／`candidate`／`gap` 不带角色）；`tsc -b`、相关 ESLint、graph i18n slice、force3d contract 通过；容器内拓扑读回与真实浏览器核对；前端镜像已重建。

边界：`annotation` 只影响图页读取投影，不改写任何拓扑数据；若某项目需要把线索链重新纳入图页，只需改回该类型的声明位置，realizer 无需改动。

## 节点名称显示修复（2026-09-26）

用户反馈“现在节点不显示名称”。核对：图页节点数据本身有内容名（读取模型派生 `content_name`，例如 `渠務署`、`洪水警報系統`、`沙田污水處理廠清洗事故`），问题出在 2D 画布的标签门槛：`label.show = showLabel && size >= 24`，而默认滑杆（节点尺寸 100%、中心化增强 0%、邻近数增强 0%）下节点尺寸恒为 `(0.2 + 4) × 4 = 16.8px`，永远达不到 24，所以勾选“显示标签”也不会出现名称。

修复：标签开关即开关。新增 `NODE_LABEL_MAX_VISIBLE_NODES = 220` 与 `NODE_LABEL_MIN_SIZE_PX = 10` 两个具名常量，`show = showLabel && visibleNodes.length <= 上限 && size >= 最小值`；叠字由系列已配置的 `labelLayout.hideOverlap` 处理，不再用一个恒高的尺寸门槛整体压掉标签。3D 侧补上 `nodeLabel`，悬停可读名称（持久文字标签需要 sprite，不在本次范围）。

实跑：`#/visual/graph/policy` 与 `#/visual/graph/market` 的香港项目画布均显示节点名称（含标签避让），无 page error；2D/3D 切换正常。截图见 `hk-node-labels-2026-09-26.png`。验证：`tsc -b`、相关 ESLint、graph i18n slice（391 keys）、force3d contract 通过；前端镜像已重建。

边界：该阈值是图页通用显示策略，不改变任何拓扑数据；节点密集时仍由渲染器按重叠隐藏，不会全部铺满。

## 画布清晰度：按显示密度渲染（2026-09-26）

用户反馈“清晰度太低了”。定位到图页 ECharts 画布在初始化时写死 `devicePixelRatio: 1`（原注释为“优先帧率而非 Retina 清晰度”），在 2x 显示屏上画布按 CSS 像素渲染后被浏览器放大，文字与细线因此发虚。`GraphWorkspace.tsx` 的另一个图表面同样写死 1。

修复：新增 `src/pages/graph/renderers/canvasPixelRatio.ts`，导出 `GRAPH_CANVAS_MAX_PIXEL_RATIO = 2` 与 `graphCanvasPixelRatio()`，按显示自身密度取比值并设上限（避免超高分屏无收益地成倍增加绘制量）；`GraphPage.tsx` 与 `GraphWorkspace.tsx` 两处初始化都改为使用它。

实跑核对（Playwright）：2x 显示下画布 backing store 从 1316 变为 2632（比值 2.0），1x 显示保持 1316（比值 1.0）；2x 下连续采样 120 帧，帧间隔中位 16.7ms、P95 17.4ms（约 60fps），未观察到渲染压力；画布文字与虚线明显变清晰。截图见 `hk-canvas-2x-2026-09-26.png`。

验证：`tsc -b`、相关 ESLint、graph i18n slice、force3d contract 通过；前端镜像已重建，页面与拓扑接口 200。

边界：上限 2 是清晰度与绘制成本的折中；若某台机器在超大图下仍感卡顿，可下调 `GRAPH_CANVAS_MAX_PIXEL_RATIO`，或后续做“交互时降密度、静止时高密度”的自适应策略，本轮未引入该状态机。

## 项目绑定的投影标签页、总图改名与香港图谱视图（2026-09-26）

用户要求：投影图谱标签页做成项目绑定；`市场实体加细图` 直接改名为 `总图`；框架改好后给香港建几个图谱。

**框架（不写香港特例）**

1. 后端 `resolve_graph_projections`（`services/graph/doc_types.py`）读取项目自定义 `field_mapping.graph_projections`，规范化为 `[{id, label?, hidden?, topology_filter?}]`，经 `GET /project-customization/graph-config` 下发；未声明的项目返回空数组。
2. 前端 `workspaceNavigation.ts` 新增 `coerceGraphProjectionBindings` / `applyWorkspaceTabBindings`：项目决定哪些入口可见、顺序与标签；未提及的入口保留在末尾，新增模块不会被静默丢弃。绑定按图入口（module key）寻址，和标签页导航使用同一身份。
3. `topologyProjection.ts` 接受 `TopologyProjectionFilter = {attribute, contains_any}`：先按属性文本取种子元素，再闭合其端点，再纳入轴端点全部在场的关系统（证据自身没有大纲节属性，靠这条规则进入对应章节视图）；注释类元素与未命中的元素不进入图。
4. `GraphPage` 的标签条、页面标题与缓存键使用绑定后的视图身份（两个绑定标签可能共享同一数据源）；`VisualizationLayerShell` 的 `h1` 也读同一份绑定，页面标题与标签一致。
5. `市场实体加细图` → `总图`：`shell.title.graphDeep` / `navigation.item.graphDeep` / `graphPage.variant.graphDeep` 三个键的中文改 `总图`，英文改 `Overview`。

**香港项目（`app/project_customization/projects/hk_water_investigation/`）**

按 `分析总纲` 的四个大纲节绑定现有入口，不新增路由：`graphDeep`=总图（无过滤）、`graphMarket`=一 供水与水资源物质基础、`graphPolicy`=二 排水河流与防洪、`graphSocial`=三 港湾填海与航道、`graphCompany`=四 社会关系、阶级意识与生活，各自 `topology_filter={"attribute":"outline_section","contains_any":[章节号]}`；`graphProduct`/`graphOperation` 隐藏；`graphBuilder` 保留为新建图谱。

**实跑结果**（标签条 6 项，逐个切换，无 page error；页面标题与标签一致，URL 仍走既有入口）：

| 视图 | 节点 | 关系 | 证据 | 主要关系名 |
| --- | --- | --- | --- | --- |
| 总图 | 909 | 914 | 548 | 管理 48／表达 40／组织 36／判断 32 |
| 一 供水与水资源物质基础 | 167 | 160 | 91 | 管理 16／分配 11／正当化 5／支配 5 |
| 二 排水河流与防洪 | 104 | 85 | 43 | 管理 12／判断 10／表达 6／依赖 5 |
| 三 港湾填海与航道 | 127 | 147 | 84 | 管理 11／组织 8／表达 6／依赖 5 |
| 四 社会关系、阶级意识与生活 | 451 | 490 | 295 | 表达 27／组织 26／中介 19／再生产 17 |

章节视图内容与总纲一致：一 供水出现东江水协议、将军澳海水淡化、水费与排污费；二 排水出现启德河、城门河、洪水警报系统、乡村防洪系统；截图见 `hk-view-ch1-supply-2026-09-26.png`、`hk-view-ch2-drainage-2026-09-26.png`。

验证：`tsc -b`、相关 ESLint、graph i18n slice（391 keys）、force3d contract、topology platform contract、layer shell contract 通过；后端重启后 `graph-config` 实读返回上述 8 条绑定；前端镜像已重建。

边界：`topology_filter` 目前支持“单属性包含任一 token”的取法加端点闭合，够表达大纲节／分池等按内容维度的视图；侧边栏导航仍是平台模块清单（未读项目绑定），项目换名只作用在标签条与页面标题；若要把侧边栏也纳入，需要把同一份绑定接到 `FigmaSideNav`，本轮未改。
