# 预发布说明：pre-release-2026-05-14-rc1

- 版本类型：`预发布（Pre-release）`
- 版本名称：`pre-release-2026-05-14-rc1`
- 发布日期：`2026-05-14`
- 适用场景：团队部署、AgentChat / Writing Workbench 联调、来源检索与本地索引验证、发布前回归
- 默认部署路径：Docker-first；本地模式用于开发调试

## 发布目标

本预发布包把当前工作树中的 Agent 运行时、写作工作台、来源检索、本地索引、前端交互和部署脚本作为一个完整项目更新交付。团队成员应能按同一套入口完成部署、健康检查、回滚演练和关键功能回归。

## 本次重点更新

### 1. AgentChat 与 Agent 运行时

- 新增 `main/backend/app/api/agent_chat.py` 作为 AgentChat API 入口。
- 新增 `agent_core` 与多组 `agent_runtime` 服务模块，覆盖会话记忆、工具契约、只读工具、控制工具、运行循环、结构化数据检索、物料本体、外部工具状态和工具池。
- 增强 Codex CLI / App Server 接入、fallback、stream 事件与长任务行为。
- 前端 `AgentChatPage` 和 `agent-chat.css` 大幅更新，覆盖长任务、工具调用、上下文压缩、项目数据工具、外部工具状态和跨页交互。

### 2. Writing Workbench 与写作回填

- 写作 API 与 `document_service` 增强版本锁、冲突详情和写回能力。
- 新增 `AgentWritingAssistantPanel`，将 AgentChat 与 Writing Workbench 的材料检索、引用、插入和写作回填链路对齐。
- 优化 Markdown 编辑器和写作工作台布局，补齐移动/桌面状态、辅助面板和材料操作状态。

### 3. 来源检索、本地索引与候选可信度

- 新增 `local_index` 服务原型与 LanceDB adapter 边界。
- 增强 Web search provider、source candidate trust、URL pool adapter 与来源库候选审批链路。
- 补充 SearXNG / YaCy 隔离部署实验与 provider benchmark 文档和运行证据。

### 4. 前端壳层、设置与项目上下文

- 更新 `AdminLayerShell`、`WorkbenchLayerShell`、`VisualizationLayerShell` 与 `useKernelRuntime`，统一项目 key、运行时状态和层级壳。
- 更新 API client、endpoint、domain API 与共享类型定义，降低前后端契约偏差。
- 补充 AgentChat、Writing Workbench、跨 flow 和长任务相关 Playwright e2e 用例。

### 5. 部署、启动与回滚

- Docker 入口仍以 `./scripts/docker-deploy.sh` 为团队默认路径。
- 本地开发入口仍以 `./scripts/local-deploy.sh` 为统一路径。
- 新增跨平台入口 `scripts/platform-macos.sh`、`scripts/platform-linux.sh`、`scripts/platform-windows.ps1`，支持本地启动、Docker 启动、图形化配置窗口和外部服务 doctor。
- 新增同一入口的跨平台小窗口 `python3 scripts/launch.py`（Windows 用 `python scripts\launch.py`），支持 Local/Docker 启停、外部服务 key 输入、本地保存和 provider 链接跳转。
- macOS 桌面小窗口补齐外部服务状态可视化、key 配置入口、Service Doctor、provider 链接和跨平台设置 UI 入口。
- 新增 `scripts/configure-external-services.py`，支持自动创建/读取 `main/backend/.env`、检测 LLM/Search/Ollama readiness、交互输入 key 并本地保存。
- Docker `--force` 启动逻辑修复：当本机 PostgreSQL/Elasticsearch/Redis 已占用 `5432/9200/6379` 时，Docker 依赖服务自动切换为容器内部端口，不再把宿主机依赖端口硬绑定失败。
- `./scripts/pre_release_min_gate.sh` 已升级为当前预发布门禁：前端 lint/build、后端关键 Agent/Writing/Search 测试、Docker 回滚演练 dry-run、metrics schema 检查和发布 hygiene 检查。
- `./main/backend/scripts/pre_release_gate.sh` 的 quick 模式已扩展到当前 Agent/Writing/Search/Local Index 关键测试集合。

## 团队部署步骤

### Docker 默认部署

```bash
cp main/backend/.env.example main/backend/.env
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh start --profile modern-ui
./scripts/docker-deploy.sh health
```

常用运维命令：

```bash
./scripts/docker-deploy.sh status
./scripts/docker-deploy.sh logs
./scripts/docker-deploy.sh checkpoint
./scripts/docker-deploy.sh rollback-drill --dry-run
./scripts/docker-deploy.sh stop
```

跨平台入口：

```bash
python3 scripts/launch.py
./scripts/platform-macos.sh docker-start
./scripts/platform-linux.sh docker-start
.\scripts\platform-windows.ps1 docker-start
```

外部服务图形化配置：

```bash
python3 scripts/launch.py
./scripts/platform-macos.sh configure
./scripts/platform-linux.sh configure
.\scripts\platform-windows.ps1 configure
```

### 本地开发部署

```bash
cp main/backend/.env.example main/backend/.env
./scripts/local-deploy.sh start
./scripts/local-deploy.sh health
```

本地前端单独运行：

```bash
cd main/frontend-modern
npm ci
VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
```

## 发布前最小门禁

```bash
./scripts/pre_release_min_gate.sh --report development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate.json
```

更严格的后端门禁：

```bash
./scripts/pre_release_min_gate.sh --strict --report development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate-strict.json
```

推荐补充前端 e2e：

```bash
cd main/frontend-modern
npm run test:e2e -- tests/e2e/agent-chat.spec.ts tests/e2e/writing-workbench.spec.ts
```

## 发布包边界

应纳入本预发布的内容：

- 后端 API、services、settings、seed data 与对应 tests。
- 前端 modern 源码、API domain、类型、样式和 e2e tests。
- `scripts/` 与 `main/ops/` 中的部署、启动、回滚、搜索实验脚本。
- `development/latest-dev-docs/` 下的当前开发索引、收口审计和 automation run 证据。
- `docs/reference-pool/platformization` 与 `ops/search-lab` 中用于本地搜索 provider 评估的说明和脚本。

不应纳入发布内容：

- 本地虚拟环境：`main/backend/.venv311/`。
- 本地运行日志：`.playwright-mcp/`。
- autonomous 执行日志：`.autonomous/`。
- 临时 clone / 外部源码目录中没有进入项目清单的内容。

## 已知风险

- Docker preflight 会在本机已有 PostgreSQL / Redis / Elasticsearch 占用 `5432 / 6379 / 9200` 时失败；这种情况下先确认是否使用本地模式，或调整 compose 端口绑定。
- 外部搜索、LLM、MCP 能力依赖本机 `.env` 与外部服务状态；无 key 或服务不可达时，应按能力降级验证基础 UI 与本地检索链路。
- `main/backend/.venv311/` 已从本预发布跟踪范围退场；团队成员需要按 README / 启动脚本在本机重建虚拟环境。

## 推荐回归清单

1. AgentChat 自由问答、项目数据工具、source approval、长任务 stream 与跨页返回。
2. Writing Workbench 材料检索、引用/插入、版本冲突和写回。
3. Source Library / Web Search / Local Index 的候选生成、可信度标注和只读检索边界。
4. Docker `preflight -> start --profile modern-ui -> health -> rollback-drill --dry-run -> stop`。
5. 本地 `local-deploy.sh start/status/health/stop`。
6. `pre_release_min_gate.sh` 生成 JSON 报告，且报告中关键阶段为 `pass` 或有明确 `skip` 理由。
