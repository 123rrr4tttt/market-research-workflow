# MRW Frontend Architecture Inventory v1

Status: `READ_ONLY_INVENTORY_OBSERVED_NOT_PROMOTION`

范围：`main/frontend-modern`（`src/`、`tests/`、`package.json`、`vite/tsconfig`）。
目标：说明当前前端逻辑形状、与 successor 后端的关系，以及「整体重构 vs 增量共享层 + 新页面接入」的判定输入。

## 0. Evidence basis

- 工作树：`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`
- 分支：`codex/functorial-successor-p0`
- HEAD（本盘点时观察）：`38acdee8862af0971ca063507b8355812894fbce`
- 盘点时间：2026-09-02（Asia/Shanghai）
- 写入边界：仅本文件；未修改其它文件，未 commit/push。
- 工作树状态：HEAD 前已存在多处 dirty 文档修改；`main/frontend-modern` 下只有
  `pnpm-lock.yaml`、`pnpm-workspace.yaml` 为未跟踪文件（盘点前已存在，本盘点未触碰）。
- 证据类型：本文件结论来自对当前 checkout 的直接源码阅读与只读检索；未在本轮重新执行
  build/test。同目录 `C9_2FrontendMilestone.v1.json` 的 `FRONTEND_IMPLEMENTED_LOCAL_ONLY`
  只作为既有证据上下文引用，不用于替代直接观察。

## 1. 技术栈与结构

### 1.1 依赖

`package.json` 显示的生产依赖：

- React 19 + React DOM 19；Vite 7 + TypeScript 5.9（strict）。
- TanStack Query v5（`@tanstack/react-query`）作为全局数据层。
- axios 作为 legacy API 请求层。
- ECharts 5 + `react-force-graph-3d` + `three`（类型依赖）负责 Graph 2D/3D 渲染。
- `@xyflow/react` 12 负责 LLM/工作流节点画布。
- `lucide-react` 图标；无额外状态库；无独立路由库；无独立 i18n 库。

主要 dev 依赖：Vite React 插件、ESLint、TypeScript、Vitest 未直接使用（仓库用
Playwright e2e）、Storybook 10 + React Vite、`@playwright/test`。

### 1.2 应用入口与路由

`src/main.tsx` 只建立 React 根、`QueryClientProvider` 和全局 QueryClient：

- 默认 `retry: 1`，`refetchOnWindowFocus: false`。
- 没有 React Router；路由是 hash 驱动的 kernel route：
  - `src/App.tsx` 先按 hash 特判 `design-concepts.html` / `concept-quiet.html` /
    `concept-monolith.html` / `concept-orbital.html` 四类概念 demo 页。
  - 其余进入 `FrontendKernelApp`。
- `FrontendKernelApp` 用 `resolveKernelRoute(hash)` 解出 `layered | legacy | default |
  unknown` 四种来源，再挂载：
  - Layer A：`WorkbenchLayerShell`
  - Layer B：`VisualizationLayerShell`
  - Layer C：`AdminLayerShell`
  - `unknown` 来源才挂 `AppShell`（legacy shell 回退）；旧 HTML hash 会先经
    `parseLegacyHashToMode` 归一化到 canonical module，再进入对应层 shell。
- `moduleManifest.ts` 是唯一的 31 模块清单；`contracts.ts`、`routes.ts`、
  `renderKernelModuleContent.tsx` 由它派生页面挂载关系。`legacyHashAdapter.ts` 再负责
  旧 HTML hash（如 `#graph.html?type=market`）到 canonical layered route 的映射。
- 31 个 kernel module 实际只对应 15 个页面组件（同一组件用 `variant` 复用在多个 module）：
  `ProcessPage`、`OpsPage`、`DashboardPage`、`GraphPage`、`IngestPage`、`RawDataPage`、
  `WritingWorkbenchPage`、`AgentChatPage`、`PolicyPage`、`CatalogPage`、
  `LlmDesignerPage`、`ProjectsPage`、`CrawlerManagePage`、`ResourcePage`、
  `SettingsPage`。另有 `ConceptLabIndexPage` 等 4 个纯 demo 页不进入 kernel。

### 1.3 状态与呈现

- 全局持久偏好（locale/theme）用 `createPersistedStore`（`useSyncExternalStore` +
  localStorage）实现，不引入 redux/zustand。
- i18n：`src/app/platform/i18n/catalog.ts` 一个 5007 行文件，手写 `zh-CN` / `en-US`
  两个目录加类型形状；无 i18next/ICU；模板插值由各页面自写 `replace(/\{...\}/...)`。
- 样式：全局 `src/index.css`（5863 行）承担几乎所有布局/panel/chip 类；另有
  `agent-chat.css`（1402）、`writing-workbench.css`（1555）、`concept-lab.css`（460）、
  `clue-chain.css`（310），总 CSS 约 9632 行；无 CSS Modules/CSS-in-JS。
- 渲染形态是典型「大页面 + 全局 class」：`GraphPage.tsx` 6226 行、
  `AgentChatPage.tsx` 2846 行、`WritingWorkbenchPage.tsx` 2838 行、
  `LlmDesignerPage.tsx` 1974 行、`OpsPage.tsx` 1405 行。

## 2. 页面/模块清单与 API 域

| 页面组件 | Kernel modules | 职责 | 主要后端/API 域 |
| --- | --- | --- | --- |
| `ProcessPage` | `overviewTasks`, `flowProcessing` | 任务列表、统计、历史、详情、日志、取消、自动刷新 | process |
| `OpsPage` | `overviewData`, `sysBackend` | 文档管理/抽取数据、governance、agent session/approval/coordinator/SSE、后端健康 | admin, governance, agent-sessions, agent-approvals, health |
| `DashboardPage` | `dataDashboard`, `dataMarket`, `dataSocial`, `flowAnalysis`, `flowBoard` | dashboard 统计/状态卡与 variant 展示 | dashboard stats |
| `GraphPage` | 8 个 `graph*` 模块（含 builder） | market/policy/social/company/product/operation/deep 图读取与 2D/3D 渲染；workflow-graph curated draft/submit/sync/rollback/audit/handoff/replay；structured search；clue chain inspector | graph/admin graph、workflow-graph、clue-chains、source-library |
| `PolicyPage` | `dataPolicy` | 政策列表/详情/统计、prompt density priority | policies, stats |
| `CatalogPage` | `dataCatalog` | topic/product 创建、列表、删除 | topics, products |
| `IngestPage` | `flowIngest`, `flowSpecialized` | 单 URL/market/policy/data-api/commodity/ecom 采集、关键词、来源库执行、agent-batch job/NL 命令/规则集、历史 | ingest, discovery, source-library, agent-batch |
| `RawDataPage` | `flowRawData` | 原始文档批量 raw import 与抽取参数 | admin documents raw-import |
| `WritingWorkbenchPage` | `flowWriting` | 文档/draft/template/citation/keyword-card/suggest/llm-action/export、typed-knowledge context、agent chat 写回 | writing, typed-knowledge, agent-chat |
| `AgentChatPage` | `flowAgentChat` | agent 对话 turn/stream、session/task/event/artifact、approval 继续/解决、capability | agent-chat, agent-sessions, agent-approvals |
| `LlmDesignerPage` | `flowLlmNodeDesign` | workflow-graph DSL compile/run/run events、节点画布 | workflow-graph |
| `ProjectsPage` | `sysProjects` | 项目 list/create/update/archive/restore/delete/activate/auto-create/inject | projects |
| `CrawlerManagePage` | `sysCrawler` | crawler project import/deploy/rollback/deploy runs | crawler |
| `ResourcePage` | `sysResource`, `flowExtract` | source library items/channels/grouped、resource pool urls/site entries、discover/recommend/simplify/bind、external project | source-library, resource-pool |
| `SettingsPage` | `sysSettings`, `sysLlm` | env/secret 配置、项目 LLM template copy/update、status intent、locale/theme | config/env, llm-config |

上述页面全部通过 `src/lib/api.ts`（legacy 聚合入口）调用，只有 `OpsPage` 直接引用
`endpoints.ts` 拼 SSE URL。页面状态基本是 `useQuery/useMutation` + `queryKeys.ts`；
`ProcessPage`/`IngestPage` 各抽了一个共享 hook（`useProcessData.ts`/`useIngestActions.ts`）。

## 3. API 层模式

### 3.1 组织

- `src/lib/api/client.ts`（178 行）：axios 实例、`X-Project-Key` 与 `project_key`
  interceptor、`ApiClientError`、`unwrapEnvelope`、`httpGet/Post/Put/Patch/Delete`、
  `asList`。全局 `market_project_key` 存在 localStorage，由页面/`useKernelRuntime`
  维护。
- `src/lib/api/endpoints.ts`：统一 `/api/v1` 字符串常量。
- `src/lib/api/services/*`：`config`/`health`/`projects`/`crawlers` 薄 wrapper。
- `src/lib/api/domains/*`：部分新分片（`project-admin`、`resource-source`、
  `clue-chains`、`graph-workflow`、`writing`、`codex-auth`、`successor-runtime`）。
- `src/lib/api.ts`（935 行）：聚合 barrel + 大量旧式本地函数（process、agent-chat、
  agent-batch、ingest、policy、catalog、llm、governance 等），是页面实际主入口。
- `src/lib/types.ts`（1735 行，158 个 `export type`）：全局共享类型。

### 3.2 请求/错误/加载样板

- 请求层：domain/service 函数反复组合 `endpoints` + `httpXxx` + `asList`/`unwrap`；
  没有单一 typed endpoint 声明表，也没有跨语言 schema 校验器；多数 decode 是
  `as`/optional field 的信任式解析。
- 错误层：axios interceptor 只对 `401 + codex_auth` 派发事件；`ApiClientError` 在
  envelope `status: error` 时抛出。页面各自做 `error instanceof Error`、
  `isApiClientError` 拼接；文案样式重复。
- 加载层：页面上分散的 `isPending/isFetching/data/error` 分支 + 刷新按钮 +
  `refetch`/`invalidateQueries`。没有通用 `useApiQuery`/`useApiMutation` 模板；只有
  process/ingest 两个局部 hook。
- 命令/异步任务：`useIngestActions` 用中文固定文案维护 `actionPending/actionMessage`，
  再逐任务人工解析 `task_id/status/rejected_count/degradation_flags`；这是异步 effect
  文案与状态在页面层手写的典型样板。

### 3.3 legacy 调用与 successor-runtime 调用差异

当前所有生产页面都走 legacy axios client；successor runtime 是另一条独立路径：

| 维度 | legacy API client | successor runtime client |
| --- | --- | --- |
| 传输 | axios、interceptor、`withCredentials` | 原生 `fetch`、无 axios |
| 项目身份 | 全局 localStorage key，自动注入 `X-Project-Key` + `project_key` query | 显式 `projectLocator`，wire 上不注入 header/query |
| envelope | `status/data/error/meta` 松散解包到 `T` | 严格 allowlist/fail-closed decode，保真返回 envelope |
| actor/scope | 无 | `actorRef` 只做校验不进 wire；server-resolved scope exact-bind |
| 幂等/去重 | 无统一机制 | command id + payload fingerprint + in-flight dedupe |
| 观测状态 | 页面自造 loading/error | 统一六态 observation |
| 类型/错误 | `types.ts` + `ApiClientError` | 文件内专用 DTO + 多层 successor error 类 |

因此 successor 前端 client 与 legacy API client 不是同构替换，而是刻意隔离的第二传输契约。

## 4. Successor 前端现状

直接检索结果：

- `src/lib/api/domains/successor-runtime.ts`（1887 行）实现：
  - `/api/v1/successor-runtime/v2/commands|queries`；
  - 六种 envelope status、六态 `deriveSuccessorUiObservation`、七个 typed
    rejection code；
  - localStorage 只存 project preference + pending command（id/kind/endpoint/
    payload digest），不存 actor/resolved scope/authority；
  - SHA-256 payload fingerprint、in-flight 去重、命令 pending 恢复、projection
    rollback receipt、freshness/clock 校验、`createSuccessorQueryRefetcher`。
- `src/components/SuccessorRuntimeObservation.tsx`（33 行）与
  `SuccessorRuntimeStatus.tsx`（47 行）是薄展示组件。
- 源码检索（排除这两个文件自身）在 `src/app/`、`src/pages/`、kernel route/manifest/
  shell 中均为 0 处引用：组件未挂到任何页面/路由。
- 两个 e2e spec（合计 2975 行，60 个 `test(`）直接 import TS 模块并 mock
  `fetch`/localStorage；检索不到 `page.goto`/browser context，因此它们不验证浏览器
  UI 挂载，只验证客户端逻辑。
- successor domain 没有从 `src/lib/api.ts` barrel re-export，页面统一入口不会碰到它。

对照同目录既有 `C9_2FrontendMilestone.v1.json`：该文件记录该里程碑为
`FRONTEND_IMPLEMENTED_LOCAL_ONLY`，且明确「observation component 未被浏览器渲染、
无 route adoption」。本盘点直接观察与之一致。

## 5. 重复与漂移点

### 5.1 页面/组件级复制

- `AppShell.tsx`（legacy shell）与 `useKernelRuntime.ts` 重复维护 health/env/
  projects/activate/inject/projectKey 逻辑；`AppShell` 只在 `unknown`/旧路由回退时
  生效，但仍是第二份运行时状态。
- `statusChipClass` 至少存在三个近似副本：`AppShell.tsx`、`AdminLayerShell.tsx`、
  `VisualizationLayerShell.tsx`；状态条与 nav 分组也在三套 shell 中复制。
- 14 个页面各自定义近同构的 `format*Template`（`formatCatalogTemplate`、
  `formatOpsTemplate`、`formatSettingsTemplate` 等）；6 个页面复制 `formatDate`；
  `CatalogPage`/`IngestPage`/`ResourcePage` 还各写 `splitTerms`。
- 生产未引用的组件：`FigmaTopNav.tsx`、`graph-kit/GraphToolbar.tsx`、
  `graph-kit/GraphLegend.tsx`、`workflow/LlmNodeDesigner.tsx`、`WritingShell.tsx`
  （只有 stories 引用）；`SuccessorRuntimeObservation/Status` 亦未挂载。存在「组件库
  与真实页面分离」的漂移：`GraphPage` 并不使用 `graph-kit` 卡片组件，而
  `OpsPage`/写作 insight 复用其中一部分。

### 5.2 API/契约复制

- `src/lib/api/domains/clue-chains.ts`（422 行，经 `lib/api.ts` barrel）与
  `src/pages/graph/clueChainClient.ts`（约 300 行，页面直接使用）实现同一
  `/api/v1/clue-chains` 域，字段/归一化逻辑各写一份；domain 版当前没有页面调用方。
- `src/lib/types.ts` 与 domain 文件分散重复 contract 类型（clue-chain、writing、
  graph-workflow 均有）；successor DTO 完全独立在
  `src/lib/api/domains/successor-runtime.ts` 内，且逐字段镜像后端 Pydantic DTO，
  没有生成/一致性检查器（人工镜像 drift 风险）。
- `queryKeys.ts` 集中但多数 key 反映页面参数而非 domain 形状；不同页面 invalidation
  集合不统一。

### 5.3 平台/配置漂移

- i18n 是手写巨型 catalog + 每页 required key 快照：11 个
  `scripts/check_*_page_i18n_slice.mjs` + disjoint gate 共约 2401 行，把同一批 key
  在 shape/zh/en/checker 中重复维护。
- 依赖管理漂移：tracked `package-lock.json`（README 走 npm）与 untracked
  `pnpm-lock.yaml`/`pnpm-workspace.yaml` 并存；既有证据记录 pnpm 在
  `approve-builds` 门禁上失败。
- 路由/壳层本身已集中到 `moduleManifest.ts`，但仍有派生副本：`moduleRegistry.ts`
  （platform/modules）、`legacyHashAdapter.ts` 各自重新构造 hash 映射。

## 6. Successor 前端判定输入

### 6.1 「整栈复制风险」

- 若 successor 新页面复制 `GraphPage`/`AgentChatPage`/`WritingWorkbenchPage` 的
  结构，将把几千行巨石页面、页面内手写 fetch/state 文案和格式 helper 一起复制，且
  会把 legacy axios `project_key` 注入语义带进 successor。
- 若每个 successor domain 新开一套 `client + types + decoder + hook + 观察组件`，
  会立刻产生 successor 内部整栈重复，违反共享基底原则。
- 当前 31-module manifest 已经让「加一个 module」成本低（manifest 一行 + render
  映射一行），但若复制整个页面栈则收益被抵消。

### 6.2 适合做共享基底的部分

- 命令/查询 envelope：`submitSuccessorCommand`/`fetchSuccessorQuery`/decode/bind
  保持单份、单一错误类型族，页面不得自行拼 `/successor-runtime/v2` JSON。
- 六态观察：`deriveSuccessorUiObservation` + `SuccessorRuntimeObservation` 是共享
  projection，允许任何 UI 消费，但只能从 phase/envelope 派生，不能伪造完成/权威。
- typed rejection：decode 只认七个 code，其余 fail-closed 为 `OUTCOME_UNKNOWN`；
  UI label/reason 由共享组件承担。
- scope/actor/idempotency：`projectLocator`、`actorRef`、command id、fingerprint、
  pending store 全部由 client 单点拥有；页面只提交业务 intent，不存取 pending/
  scope/authority。
- 查询只读：refetcher/query hooks 必须保持 read-only，绝不能从 refetch 触发
  command/control。
- 可抽一个薄 React adapter：`useSuccessorQuery`/`useSuccessorCommandObservation`，
  内部统一 TanStack Query key、phase/envelope -> observation、typed rejection
  message，使新页面只写业务投影。

### 6.3 legacy 前端保留还是投影

- 当前 legacy 页面是实际生产 UI，且后端 legacy 路由仍保留 310 条（见既有
  route-mount 证据；本盘点未重跑后端）。在 successor 达到 shadow parity 且
  projection 可读之前，应把 legacy 前端保留为 canonical UI，不整体替换。
- 可以增量把某页的只读数据切到 successor query projection，但前提是该 cell 的
  projection snapshot/scope 已真实可用；命令仍应等待 approval/authority 语义与
  canonical write 接线后再接入生产页面。

## 7. 结论建议（供主 Agent 裁决）

结论：当前不需要对 legacy 前端做整体重构，也不应直接宣告 successor 前端替换。
推荐路径是「保留 legacy 页面 + 增量共享 successor 基底 + 一个受控 vertical slice」。

理由：

1. 前端生产路径全部绑定 legacy axios/API；successor client 是独立、未挂载的
   `FRONTEND_IMPLEMENTED_LOCAL_ONLY` 包，没有页面/路由依赖。
2. 前端真正可复用的 successor 资产（fail-closed envelope、六态、typed rejection、
   idempotency/scope）已经集中在 `successor-runtime.ts`；下一步应加薄 hooks/UI
   共享层，而不是复制它。
3. 现有巨石页面与 shell/i18n 重复是维护成本，但重写它们需要后端 parity 与
   projection 支撑；在无 successor 生产数据时整栈重构只会放大风险。

迁移顺序建议：

1. 固定 legacy 前端为当前 canonical UI，补 page/API 调用矩阵与 minimal
   route/API 回归证据（不搬页面代码）。
2. 从 `successor-runtime.ts` 提取只读共享层：typed query/command options、六态
   hook、rejection 展示、scope/idempotency 单点；先在 node/e2e 层验证。
3. 选一个最小 successor vertical slice（不是 Graph/AgentChat/Writing），在 kernel
   manifest 下新增 local-only 页面入口，复用现有 shell/module 配置，只接 successor
   command/query 与 observation。
4. slice 通过后，再按 domain 评估 legacy 页面 read-model 投影；命令类切换必须等
   approval/canonical write 授权边界闭合。
5. 全程避免把 successor 函数混入 `src/lib/api.ts` 或 legacy axios interceptor；
   保持 transport/authority 语义隔离。

关键冲突文件（如需改 route/页面/壳层）：

- `src/app/kernel/moduleManifest.ts`、`contracts.ts`、`renderKernelModuleContent.tsx`
  （新 module 注册）。
- `src/app/kernel/useKernelRuntime.ts` + `src/app/shell/AppShell.tsx`（重复 project/
  status 运行时，先定 canonical）。
- `src/lib/api.ts` / `src/lib/api/client.ts`（不要把 successor 混入 legacy interceptor）。
- `src/lib/api/domains/successor-runtime.ts`（唯一 successor transport 所有者）。
- `src/lib/queryKeys.ts`、`src/app/platform/i18n/catalog.ts`、对应 i18n slice scripts。
- `src/index.css` 及巨石页对应 CSS。
- `package.json`/lockfile 与 `pnpm-workspace.yaml` 的依赖管理裁决。

## Appendix A. 关键文件指纹（本盘点计算）

```text
src/lib/api.ts                                  ba775c94da23ec1fc6f3a90922f15253a046b5f4270fc29845f1fcc4e7c13005
src/lib/types.ts                                4d4ae7a2a676fbcf8319610bf494c336365d6490b99025296bf7ba2b24351f45
src/lib/api/client.ts                           d65ad6875b3334e6149c28daa201188b341c4d123cc8ffa4f1d397794bdfe6f7
src/lib/api/endpoints.ts                        48292ca224bd3dc6587a1800606ff3dbb55714feb7361b20d4cd49b5c3009cc4
src/lib/api/domains/successor-runtime.ts         cfd390ee67a183e9052a802e79ed0e33da492c3bafb7bdbf27c757a500901436
src/components/SuccessorRuntimeObservation.tsx   c88c30aa6ddbef9135d6cb720bb95a9f7bfbe5d59541be10dce157f952c1a533
src/components/SuccessorRuntimeStatus.tsx        31b6a2abd43bc263c6add5a67c0ca7d7582117083e025ca96552151dde11b893
src/pages/graph/clueChainClient.ts              4ec1bdff870b1e99d6392c12263daeb2ba7b1625ac249a94ee18575059c6c1f8
src/lib/api/domains/clue-chains.ts              e8239af8ea8c812ad79f958cfe6e4a313d64c97824e907cd7978017faa427cdf
tests/e2e/successor-runtime-client.spec.ts      f3d423b6be77b4578682c224d04d27f4d82b44bc0c2dc0fa94295f6bbd7c7065
tests/e2e/successor-runtime-observation.spec.ts 0c822a1b1e6f5cee6cd87bd3e3bc51f7170cf8a32de41b649a67544d1322810d
```

这些 SHA 只证明盘点对象为该字节版本；不证明 build/test、运行期或生产完成。
