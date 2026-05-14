# Optional Search / Index Enhancements Launcher Integration

更新时间：2026-05-14 PST  
状态：已实现并完成静态验证

## 目标

将 SearXNG、YaCy、LanceDB 从隔离实验入口提升为项目级可选增强：

- 默认启动路径不改变。
- 用户可在跨平台启动窗口中勾选增强项。
- SearXNG / YaCy 作为主 compose 的可选 Docker 服务启动。
- LanceDB 作为可选 Python 依赖安装，不进入基础依赖列表。
- 后端已有显式 provider / local index adapter 继续复用，不把 SearXNG / YaCy 加入 `provider=auto`。

## 实现落点

| 范围 | 文件 | 说明 |
|---|---|---|
| 跨平台启动窗口 | `scripts/launch.py` | 新增 `Optional Startup Enhancements` 勾选项：SearXNG、YaCy、LanceDB；Start Local / Start Docker 自动透传 `--with-*` |
| 跨平台跳转 | `scripts/launch.py` | 增加 Local UI、Docker UI、Docker Launcher、Codex Auth 图形化入口；业务 Docker 前端固定指向 `http://localhost:5174`，Docker Launcher 独立指向 `http://localhost:5176` |
| macOS 包装窗口 | `tools/macos/Launcher.swift` | 新增同名勾选项与状态监控；本地 / Docker 启动命令继承勾选参数；API 设置为原生 SwiftUI sheet；补充 Docker UI、Codex Auth 和外部 provider 控制台跳转 |
| 可选服务管理 | `scripts/optional-enhancements.sh` | 新增统一 start / stop / status / install-lancedb 入口 |
| 本地启动 | `scripts/local-deploy.sh`、`main/backend/start-local.sh` | 支持 `--with-searxng`、`--with-yacy`、`--with-lancedb`；LanceDB 只在勾选时安装 |
| Docker 启动 | `scripts/docker-deploy.sh`、`main/ops/start-all.sh`、`main/ops/restart.sh` | `--with-searxng/--with-yacy` 映射到 `search-enhancements` profile；`--with-lancedb` 触发可选依赖 build |
| Compose | `main/ops/docker-compose.yml` | 新增 `searxng` / `yacy` 可选服务与后端默认内部 URL |
| 依赖 | `main/backend/requirements-optional-enhancements.txt` | `lancedb==0.24.2` 独立于基础 `requirements.txt` |
| 配置 | `main/backend/.env.example`、`scripts/configure-external-services.py` | 增加 SearXNG / YaCy 可选增强配置项 |
| Provider Links | `tools/macos/Launcher.swift`、`scripts/launch.py` | OpenAI、Azure、Ollama、Serper、Google CSE、SerpApi、Serpstack、Bing、LegiScan、Twitter/X、SearXNG、YaCy 均可从设置页直接打开 |
| Codex Auth | `tools/macos/Launcher.swift`、`scripts/launch.py`、`main/backend/.env.example`、`main/backend/Dockerfile`、`main/ops/launcher-agent/`、`main/ops/launcher-ui/` | 增加 Codex OAuth 配置字段、`/api/v1/codex-auth/login?next_url=...` 跳转入口，以及 Docker Web Launcher 中的 Codex CLI bootstrap 按钮 |
| Docker Web Launcher | `scripts/docker-launcher-ui.sh`、`scripts/docker-app-control.sh`、`main/ops/launcher-agent/`、`main/ops/launcher-ui/`、`main/ops/docker-compose.yml` | 新增 Docker 模式的跨平台 Web 启动器：`launcher-ui` 运行在独立 `5176` 控制面端口，经白名单 `launcher-agent` 控制当前 compose project；业务前端 `frontend-modern` 继续运行在 `5174`；业务服务 start / stop 与控制面 start / stop 分离；控制界面与 macOS App 对齐到 Docker 运行概览、可选增强、Runtime Monitor、Codex Auth、独立 API Settings 和外部 provider 跳转，不包含本地启动控制 |

## 启动方式

跨平台窗口：

```bash
python3 scripts/launch.py
```

命令行本地模式：

```bash
./scripts/local-deploy.sh start --with-searxng --with-yacy --with-lancedb --force
```

命令行 Docker 模式：

```bash
./scripts/docker-deploy.sh start --profile modern-ui --with-searxng --with-yacy --with-lancedb --force
```

Docker Web Launcher 控制面：

```text
http://localhost:5176
```

说明：该页面运行在独立 `launcher-ui` 容器中，适合作为 Windows / Linux / Docker Desktop 的统一启动器前端。它不是从容器反向弹宿主机原生窗口，而是通过 `launcher-agent` 代理控制当前 compose project。点击 Docker 启动时只启动 `launcher-agent` + `launcher-ui` 控制面；业务服务 `db` / `es` / `redis` / `backend` / `celery-worker` / `frontend-modern` 由 Web Launcher 内部按钮继续启动或关闭。

控制面隔离：`scripts/docker-launcher-ui.sh` 使用独立 compose project `mrw-launcher` 启动 `launcher-agent` / `launcher-ui`。业务栈仍使用 `main/ops` 默认 project `ops`。这样 Docker Desktop 中业务 project 的 start / stop 不应再成为启动器控制面的默认生命周期；如果用户直接点击 Docker Desktop 里的 `ops` project Start，Docker 仍可能恢复业务容器，这是 Docker Desktop 原生行为，不等同于本项目的“Docker Launcher”按钮。

Docker Desktop 自动弹窗：容器本身不能直接调用 macOS 浏览器，因此 macOS 通过 `scripts/docker-launcher-url-watcher.sh` + `scripts/install-docker-launcher-url-watcher.sh` 安装 LaunchAgent。该 watcher 监听 `mrw-launcher` project 中 `launcher-ui` 容器的 Docker start 事件，并在宿主机自动打开 `http://127.0.0.1:5176`。日志位于 `~/Library/Logs/MarketResearchWorkflow/docker-launcher-url-watcher.*.log`。

Linux 桌面自动弹窗依赖宿主机 `xdg-utils` 包提供的 `xdg-open`。该依赖已纳入 Docker preflight 检查：检测到 Linux 图形桌面会话且缺少 `xdg-open` 时提示安装 `xdg-utils`；无桌面 / headless 环境仅输出 URL，不强制要求该依赖。

Docker Web Launcher 对齐内容：

- Docker App 运行概览：核心服务在线比例、App / Control 服务计数。
- 可选增强勾选：SearXNG、YaCy；LanceDB 保留为后端可选依赖提示，不在 Docker Web Launcher 内直接安装。
- Runtime Monitor：`db`、`es`、`redis`、`backend`、`celery-worker`、`frontend-modern`、`searxng`、`yacy` 每项均可点击启动 / 停止。
- 快捷跳转：App UI、API Docs、独立 API Settings、Codex Auth。
- API Settings：由 `launcher-ui` 自己提供 `/settings.html`，通过 `launcher-agent` 受控代理读写 Docker backend 的 config API；读取时密钥字段只返回脱敏值，不跳转到业务前端 `5174/settings`。
- Docker Codex Auth：Docker Web Launcher 的 Codex Auth 按钮不要求用户手动输入 token；按钮调用 `launcher-agent -> backend /api/v1/codex-auth/cli/bootstrap`。backend 若未检测到 Codex CLI，会按 `CODEX_CLI_INSTALL_COMMAND=auto` 从 OpenAI Codex GitHub Release 下载当前 Linux 架构对应的单文件二进制到 `/root/.codex/bin/codex`，再执行 `codex login --device-auth` 并把认证 URL / device code 返回给宿主机浏览器页面打开。
- 外部 provider 跳转：OpenAI、Azure、Ollama、Serper、Google CSE、SerpApi、Serpstack、Bing、LegiScan、Twitter/X。
- 不包含本地启动、本地 backend/frontend/worker 控制；这些仍由 macOS 原生 App 或跨平台 Tk 启动器负责。

状态检查：

```bash
./scripts/optional-enhancements.sh status
./scripts/local-deploy.sh status
```

## 边界

- SearXNG / YaCy 是显式 provider，只在 agent / API 指定 `provider=searxng` 或 `provider=yacy` 时使用。
- `provider=auto` 仍维持既有外部搜索排序，不自动进入本地开源 provider。
- LanceDB 只作为本地索引 adapter 的可选依赖，不替代全项目数据向量化 / 标准化路线。
- `ops/search-lab/` 保留为 benchmark / smoke / 官方文档对齐证据目录；运行入口已迁到 `main/ops/docker-compose.yml` 和启动窗口。
- `launcher-agent` 挂载 `/var/run/docker.sock`，因此只能暴露白名单 API；禁止把任意 shell / Docker command 透传给前端。
- `launcher-agent` 的 compose 启动依赖 `HOST_PROJECT_ROOT` 与宿主机实际项目根一致；当前默认值为本机仓库路径，跨平台打包时需要由平台脚本写入。
- `launcher-agent` / `launcher-ui` 是控制面服务，不计入业务运行服务数量；Web Launcher 的 Stop App 只停止业务服务和可选增强服务，不能关闭自身。
- `frontend-modern` 的 Docker 业务前端端口保持 `5174`，不作为启动器控制面端口使用。
- Docker 内 Codex 适配边界：容器不能直接弹出宿主机原生浏览器；正确流程是容器生成 device auth URL，`launcher-ui` 在用户当前宿主机浏览器标签页中打开。backend 镜像不内置 `nodejs` / `npm`；Docker 默认使用 GitHub Release 单文件二进制安装路径，Codex CLI 与认证文件通过 compose 命名卷 `codex_auth:/root/.codex` 持久化。
- `launcher-ui` 不再直通代理 backend `/api/v1/*`；配置读写必须经过 `launcher-agent` 白名单代理，避免 API key 等敏感值绕过脱敏返回。

## 验证

已执行：

```text
bash -n scripts/optional-enhancements.sh scripts/local-deploy.sh scripts/docker-deploy.sh scripts/platform-macos.sh scripts/platform-linux.sh main/ops/start-all.sh main/ops/stop-all.sh main/ops/restart.sh main/backend/start-local.sh
python3 -m py_compile scripts/launch.py scripts/configure-external-services.py
swiftc -parse tools/macos/Launcher.swift
docker compose -f main/ops/docker-compose.yml --profile modern-ui --profile search-enhancements config
HOST_PROJECT_ROOT=/Users/wangyiliang/market-research-workflow docker compose -f main/ops/docker-compose.yml --profile modern-ui config
./scripts/optional-enhancements.sh status
./scripts/local-deploy.sh status
bash scripts/build-macos-launcher.sh
npm run build
python3 -m py_compile main/ops/launcher-agent/launcher_agent.py
```

补充说明：`./scripts/docker-deploy.sh preflight --profile search-enhancements` 在当前机器因本地 PostgreSQL 已占用 `5432` 提前停止；compose config 已通过，未强行停止正在运行的本地服务。
