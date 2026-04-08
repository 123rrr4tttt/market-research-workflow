# frontend-modern

React + Vite 新前端栈（Docker-first），用于替代旧模板前端。

## 已完成（本轮）

- 迁移 `ingest` 核心参数：
  - 查询词、专题联想、语言、provider、max_items、start_offset、days_back
  - `enable_extraction`、`async_mode`
  - 社交参数：`platforms`、`base_subreddits`、`enable_subreddit_discovery`
  - 来源库执行：`item_key` / `handler_key` + `override_params`
  - 商品、电商采集参数
- 视觉升级 V2：深色侧栏 + 高对比卡片 + 渐变背景 + 强层级数据面板（偏 n8n/办公后台风格）

## 1) 本地开发

```bash
npm install
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

默认会将 `/api/*` 代理到 `VITE_API_PROXY_TARGET`（未设置时为 `http://localhost:8000`）。

## 1.1) E2E 测试（Playwright）

```bash
npx playwright install
npm run test:e2e
# 可视化模式
npm run test:e2e:headed
```

测试会自动拉起本地前端（`http://127.0.0.1:4173`）并执行 `tests/e2e/` 下用例。

## 1.2) Storybook + MCP

```bash
npm run storybook
```

- 默认访问地址：`http://localhost:6006`
- 本地 MCP 入口：`http://localhost:6006/mcp`
- Storybook 现在作为 agent-facing contract surface 使用，默认分三类 story：
  - `Component Stories`：纯展示与高复用组件
  - `Container Stories`：带 query / mutation / 行为的工作单元
  - `Shell Stories`：挂在真实 workbench / visualization / management 壳层下的高保真页面
- 热点页已经切到 MCP-first 分组与矩阵：
  - `Pages/Workbench/IngestPage`
  - `Pages/Workbench/WritingWorkbenchPage`
  - `Pages/Visualization/GraphPage`
  - `Pages/Management/SettingsPage`
  - `Pages/Management/ProcessPage`
  - `Pages/Workbench/LlmDesignerPage`
  - 上述 story 统一提供 `Container` + `Shell` 入口，并补了 loading / empty / error / mode-diff / realistic data 等状态
  - 其中 `SettingsPage`、`ProcessPage` 与 `IngestPage` 已进一步抽出真实 `View` 组件，MCP 可直接消费 `View Default` story
  - `LlmDesignerPage` 在 Storybook 中默认走 `storybook-lite` 入口，只保留 agent 所需 contract surface；完整 ReactFlow runtime 仍保留在应用路径
- Storybook 与三层架构共享：
  - `src/app/kernel/moduleManifest.ts`
  - `src/app/kernel/legacyHashAdapter.ts`
  - `src/pages/storybookKernelUtils.tsx`
- 当前首批 story 覆盖：
  - `src/components/Gv2NodeCard.stories.tsx`
  - `src/components/GraphBusinessCardSections.stories.tsx`
  - `src/components/GraphExtensionsSections.stories.tsx`
  - `src/components/FigmaTopNav.stories.tsx`
  - `src/components/FigmaSideNav.stories.tsx`
  - `src/components/graph-kit/GraphShapeBadge.stories.tsx`
  - `src/components/graph-kit/GraphLegend.stories.tsx`
  - `src/components/graph-kit/GraphNodeCard.stories.tsx`
  - `src/components/graph-kit/GraphToolbar.stories.tsx`
  - `src/components/workflow/NodeTemplatePalette.stories.tsx`
  - `src/components/workflow/NodeInfoCard.stories.tsx`
  - `src/components/workflow/LlmNodeDesigner.stories.tsx`
  - `src/components/writing/CitationBasket.stories.tsx`
  - `src/components/writing/KeywordInsightSidebar.stories.tsx`
  - `src/components/writing/LlmAssistantPanel.stories.tsx`
  - `src/components/writing/MarkdownEditor.stories.tsx`
  - `src/components/writing/MarkdownPreview.stories.tsx`
  - `src/components/writing/TemplateLibraryPanel.stories.tsx`
  - `src/components/writing/WritingInsightCard.stories.tsx`
  - `src/components/writing/WritingShell.stories.tsx`
  - `src/pages/ConceptLabIndexPage.stories.tsx`
  - `src/pages/ConceptQuietPage.stories.tsx`
  - `src/pages/ConceptMonolithPage.stories.tsx`
  - `src/pages/ConceptOrbitalPage.stories.tsx`
  - `src/pages/WritingWorkbenchPage.stories.tsx`
  - `src/pages/AgentChatPage.stories.tsx`
  - `src/pages/CatalogPage.stories.tsx`
  - `src/pages/CrawlerManagePage.stories.tsx`
  - `src/pages/DashboardPage.stories.tsx`
  - `src/pages/GraphPage.stories.tsx`
  - `src/pages/IngestPage.stories.tsx`
  - `src/pages/LlmDesignerPage.stories.tsx`
  - `src/pages/OpsPage.stories.tsx`
  - `src/pages/PolicyPage.stories.tsx`
  - `src/pages/ProcessPage.stories.tsx`
  - `src/pages/ProjectsPage.stories.tsx`
  - `src/pages/RawDataPage.stories.tsx`
  - `src/pages/ResourcePage.stories.tsx`
  - `src/pages/SettingsPage.stories.tsx`

静态构建：

```bash
npm run storybook:build
```

## 2) Docker 运行

```bash
docker build -t market-frontend-modern .
docker run --rm -p 5174:80 --network <your-compose-network> market-frontend-modern
```

容器内 Nginx 已将 `/api/*` 反向代理到 `http://backend:8000`。
默认建议不设置 `VITE_API_BASE_URL`（保持空值），前端将继续使用同源 `/api/*` 并走 Nginx 反代。

## 3) docker-compose 示例

```yaml
services:
  frontend-modern:
    build:
      context: ./main/frontend-modern
      args:
        VITE_API_BASE_URL: ${VITE_API_BASE_URL:-}
    ports:
      - "5174:80"
    depends_on:
      - backend
    networks:
      - default

# 使用仓库内 compose
docker compose -f main/ops/docker-compose.yml --profile modern-ui up -d frontend-modern

默认情况下（compose 中 backend 已设置 `MODERN_FRONTEND_URL=http://localhost:5174`），访问 `http://localhost:8000/`、`/app`、`/app.html` 会重定向到 modern 前端。

变量说明：
- `VITE_API_PROXY_TARGET`：仅本地 `npm run dev` 代理目标。
- `VITE_API_BASE_URL`：前端构建期变量，写入静态产物；不设置时保持当前相对路径行为。
```

## 4) 对齐的核心 API

- `GET /api/v1/health`
- `GET /api/v1/projects`
- `POST /api/v1/projects/{project_key}/activate`
- `POST /api/v1/discovery/generate-keywords`
- `POST /api/v1/ingest/policy/regulation`
- `POST /api/v1/ingest/market`
- `POST /api/v1/ingest/data-api`
- `POST /api/v1/ingest/commodity/metrics`
- `POST /api/v1/ingest/ecom/prices`
- `POST /api/v1/ingest/source-library/sync`
- `POST /api/v1/ingest/source-library/run`
- `GET /api/v1/ingest/history`
- `GET /api/v1/source_library/items`
- `GET /api/v1/resource_pool/site_entries/grouped`

接口盘点见：
- `../backend/docs/API_ROUTE_INVENTORY_2026-02-27.md`
- `../backend/docs/FRONTEND_MODERNIZATION_API_MAP_2026-02-27.md`
