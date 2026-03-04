# 链路7：Frontend Platformization（legacy + modern 共存）

## 1) 现状（legacy + modern 并存）

### 1.1 入口与路由形态
- 后端 `main/backend/app/web_ui_routes.py` 已实现“优先 modern、兜底 legacy archived”模式：
  - `MODERN_FRONTEND_URL`（或 `MODERN_FRONTEND_HOST/PORT`）可用时，`/`、`/app.html` 等入口 `302` 到 modern。
  - legacy 页面路由（如 `/dashboard.html`、`/graph.html`、`/process-management.html`）会被转发为 modern 的 hash 路由（`/#...`）。
  - modern 关闭时返回 `410 Legacy UI 已封存`，说明 legacy 仅保留审计/回滚价值。
- `main/frontend/templates/ARCHIVED.md` 明确：templates 目录不再作为默认运行时 UI，仅归档。

### 1.2 modern 前端的“兼容壳”定位
- `main/frontend-modern/src/app/shell/AppShell.tsx` 采用单壳（React + React Query）承接 legacy hash，统一渲染新页面组件。
- `main/frontend-modern/src/app/navigation/index.ts` 已建立 legacy URL 片段到 `NavMode` 的映射（如 `#process-management.html -> overviewTasks`，`#graph.html?type=policy -> graphPolicy`）。
- 现阶段本质是“单体壳 + 页面级兼容映射”，还不是严格的微前端拆分。

## 2) 开源替代参考池（3-5 个）

> 覆盖要求：micro-frontend（含）、BFF（含）、design system（含）

| 方案 | 类别 | 适配价值 | 官方链接 |
|---|---|---|---|
| single-spa | Micro-frontend 编排 | 最适合“页面级绞杀”：保留 legacy 路由，同时把 modern 页面按应用注册并逐步替换 | https://single-spa.js.org/ |
| Module Federation（Webpack） | Micro-frontend 运行时模块共享 | 适合将图谱、采集、设置等域拆成独立构建与发布单元，保留统一壳与共享依赖 | https://webpack.js.org/concepts/module-federation/ |
| qiankun | Micro-frontend（single-spa 生态） | 国内团队常用，主应用可托管多个子应用，利于 legacy/modern 长期并行治理 | https://qiankun.umijs.org/ |
| Next.js（Route Handlers） | BFF | 可把前端聚合 API、鉴权、缓存下沉到 BFF 层，降低前端直连后端 API 的耦合 | https://nextjs.org/docs/app/building-your-application/routing/route-handlers |
| Ant Design | Design System | 可为 modern 与后续子应用提供统一设计 token/组件规范，减少并存期 UI 漂移 | https://ant.design/ |

## 3) 路由 / 状态 / 接口层 IO 映射

### 3.1 路由 IO（入口 -> 前端状态）
| 输入（URL） | 中间层行为（backend） | 输出（modern 壳状态） |
|---|---|---|
| `/`、`/app.html` | `302` 到 `MODERN_FRONTEND_URL/` | AppShell 启动，默认 `defaultNavMode` |
| `/process-management.html` | 重写到 `/#process-management.html` | `parseLegacyHashToMode -> overviewTasks/flowProcessing` |
| `/graph.html?type=policy` | 重写到 `/#graph.html?type=policy` | `NavMode=graphPolicy`，渲染 `GraphPage` |
| `/raw-data` | alias -> `/raw-data-processing.html` 再转发 | `NavMode=flowRawData`，渲染 `RawDataPage` |

### 3.2 状态 IO（浏览器状态 -> 请求上下文）
| 输入 | 转换 | 输出 |
|---|---|---|
| `localStorage.market_project_key` | `normalizeProjectKey` | 请求头 `X-Project-Key` |
| 前端请求 `/api/*` | axios request interceptor | 自动附加 `?project_key=<key>` |
| `window.location.hash` | `parseLegacyHashToMode` | `viewMode`（页面组件选择） |

### 3.3 接口 IO（API envelope）
| 输入 | 规则 | 输出 |
|---|---|---|
| 后端返回 `{status,data,error,meta}` | `unwrapEnvelope` | `status=ok` 返回 `data` |
| 后端返回 `status=error` | `ApiClientError` | 统一错误码/消息/细节透传 |

## 4) 渐进迁移路线（页面级绞杀）

1. 先固化“壳优先”
- 保持所有 legacy 入口继续可访问，但统一 302/alias 到 modern hash（现有机制已具备）。
- 新功能只进 modern（templates 仅留回滚审计）。

2. 按业务域拆页面子应用
- 第一批建议：`graph`、`ingest/process`、`settings/resource`。
- 采用 `single-spa` 或 `Module Federation`，每个域独立构建，壳负责导航与公共上下文（project_key、鉴权、主题）。

3. 引入 BFF 聚合层
- 将跨域组合查询（dashboard、graph 汇总）前移到 BFF，前端减少 N 次散请求。
- BFF 统一处理缓存、限流、灰度字段，降低 legacy/modern 接口差异成本。

4. Design System 平台化
- 先抽 token（色彩/间距/字体）与高频组件（导航、表格、表单、状态标签）。
- 壳与子应用共享 DS 包，避免并存期 UI 进一步分叉。

5. 退役 legacy 页面
- 当某页面 modern 覆盖并稳定后，对应 `.html` 路由返回永久重定向或 410（分批执行）。
- 最终仅保留历史快照与回滚开关，不再承载运行流量。

## 5) 最小 PoC 命令

### 5.1 验证当前“页面级绞杀”基线（本仓即可）
```bash
# 终端1：启动后端（示例）
cd main/backend
uvicorn app.main:app --reload --port 8000
```

```bash
# 终端2：启动 modern 前端
cd main/frontend-modern
npm run dev -- --host 127.0.0.1 --port 5173
```

```bash
# 终端3：验证 legacy 路由被转发到 modern hash
curl -I "http://127.0.0.1:8000/process-management.html"
curl -I "http://127.0.0.1:8000/graph.html?type=policy"
# 期望: 302 Location: http://127.0.0.1:5173/#process-management.html
#      302 Location: http://127.0.0.1:5173/#graph.html?type=policy
```

### 5.2 single-spa 页面级 PoC（独立沙箱）
```bash
npx create-single-spa@latest
# 选择 root-config + 一个 react 子应用（如 graph）
# 将现有 graph 页面逻辑迁入子应用，并由 root-config 挂载到 /graph 相关路由
```

