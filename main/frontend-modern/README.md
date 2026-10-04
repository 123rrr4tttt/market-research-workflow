# MRW 前端

React + TypeScript + Vite 前端，提供工作台、可视化与管理界面；Agent 页面使用 Codex WebUI。整栈启动、端口和认证见 [日常使用指南](../../docs/usage.md)，系统关系见 [架构入口](../../docs/architecture/README.md)。

## 本地开发

以下命令从仓库根目录进入前端目录执行。项目 Docker 构建和 Playwright 启动命令使用 pnpm。

```bash
cd main/frontend-modern
pnpm install --frozen-lockfile
pnpm dev
```

Vite 默认端口为 `5173`（可通过 `PORT` 修改）。`/api` 默认代理到 `http://localhost:8000`；`/codex` 默认代理到 `http://127.0.0.1:8172`，包含 WebSocket 转发。需要连接其他本地服务时显式指定目标：

```bash
VITE_API_PROXY_TARGET=http://localhost:8000 \
VITE_CODEX_PROXY_TARGET=http://127.0.0.1:8172 pnpm dev
```

代理配置见 [vite.config.ts](vite.config.ts)。`VITE_API_BASE_URL` 是构建期变量；使用同源 `/api` 时保持空值。

## 检查与构建

命令定义见 [package.json](package.json)。

```bash
pnpm lint
pnpm exec tsc -b
pnpm build
pnpm preview
```

`build` 包含 TypeScript 检查和 Vite 构建。`preview` 用于预览构建产物；整栈 Docker 运行方式统一见使用指南。

## Playwright

```bash
pnpm exec playwright install chromium
pnpm test:e2e
pnpm test:e2e:headed
```

[playwright.config.ts](playwright.config.ts) 使用 Chromium，自动启动独立 Vite 服务，默认地址为 `http://127.0.0.1:4173`；通过 `FRONTEND_E2E_PORT` 可指定其他空闲端口。测试不复用已有服务。默认将 API 和 Codex 代理指向未监听的本地端口，用例自行 mock；真实后端测试必须显式设置两个代理目标：

```bash
VITE_API_PROXY_TARGET=http://localhost:8000 \
VITE_CODEX_PROXY_TARGET=http://127.0.0.1:8172 \
pnpm test:e2e:real-backend-business-lines
```

用例位于 [tests/e2e](tests/e2e/)，真实后端测试所需服务与数据由相应用例规定。

## Storybook

```bash
pnpm storybook
pnpm storybook:build
```

开发地址为 `http://localhost:6006`，MCP 入口为 `/mcp`。配置见 [.storybook/main.ts](.storybook/main.ts)，按 `src/**/*.stories.ts(x)` 收集组件、容器和页面故事；组件行为与状态在对应 story 维护。

## 源码入口

| 入口 | 职责 |
|---|---|
| [src/main.tsx](src/main.tsx)、[src/App.tsx](src/App.tsx) | 应用挂载与初始化 |
| [src/app/kernel/FrontendKernelApp.tsx](src/app/kernel/FrontendKernelApp.tsx) | 三层界面壳与模块装配 |
| [src/app/kernel/moduleManifest.ts](src/app/kernel/moduleManifest.ts) | 模块注册与导航声明 |
| [src/lib/api](src/lib/api/) | API 客户端与领域调用 |
| [src/pages](src/pages/)、[src/components](src/components/) | 业务页面和复用组件 |
| [src/pages/CodexAgentPage.tsx](src/pages/CodexAgentPage.tsx) | Codex WebUI 包装页与认证状态 |

进一步开发见 [开发指南](../../docs/development/README.md)；Codex WebUI 的独立宿主与配置见 [WebUI README](../ops/codex-webui/README.md)。
