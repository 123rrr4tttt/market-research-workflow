# 本地与容器运行入口

## 本机日常运行

当前宿主日常链路由业务前端、后端 API、Codex WebUI、launchd 管理的 Celery worker 和
Elasticsearch 组成。访问地址为前端 <http://127.0.0.1:5173>、API
<http://127.0.0.1:8000/docs>、Codex WebUI <http://127.0.0.1:8172>。OAuth 身份由宿主
`~/.codex/auth.json` 共享给 WebUI；WebUI home 是 `~/.codex-mrw-agent`，并通过共享
symlink 读取宿主身份。当前全链路证据见
[`.data/readiness-repair/20261004-daily-chain/daily-chain-state.json`](../../.data/readiness-repair/20261004-daily-chain/daily-chain-state.json)。结构整理后的服务重载、正式worker材料链和WebUI浏览器读回见
[结构整理实施结果](../../docs/development/MRW结构整理方案与分发包.md#8-实际实施进度)。

本机 HTTP loopback 的 Agent 对话页固定嵌入 `http://localhost:8172/`。WebUI 仅为真实
loopback 且不含转发头的浏览器请求 bootstrap 自身 JWT。后端显式开启
`CODEX_WEBUI_LOCAL_SINGLE_USER_ENABLED=true` 后，只把同样来自真实 loopback、携带匹配
`X-MRW-Server-API-Key` 且无转发头的原始 `record-input` / `dispatch` 请求投影为稳定
`local_host` actor；项目、线程、turn、批准和 grant 继续由原宿主合同校验。MRW auth
状态查询只更新提示，不因会话到期、后端重启或查询失败重载对话 iframe。非本机入口仍
要求 MRW 浏览器会话，并使用原 `/codex/` 认证代理。

胞腔宿主通过 `MRW_BACKEND_URL` 调用同一业务环境的 `/api/v1/agent-macro-host`，
`MRW_BACKEND_API_KEY` 须与该后端的 `CODEX_WEBUI_SERVER_API_KEY` 一致；两者仅在
服务端使用，不传浏览器或模型。`start.sh` 复用原私密 LaunchAgent 配置，默认使用
宿主 API。当前 Docker 页面 `http://127.0.0.1:5174` 与宿主 `127.0.0.1:8000`
可能连接不同数据库；该页面的 WebUI 接线应显式设置
`MRW_BACKEND_URL=http://127.0.0.1:5174`，不凭相同 project key 混用资料。

前端向 iframe 传递用户选定项目；WebUI 创建新线程前 prepare 工具环境，线程创建后
绑定独立 MRW session。切换项目只影响新线程。权限确认留在同一聊天窗口，精确绑定
待执行工具、参数、项目和包摘要；未确认时不执行 handler。stdio 兼容目录可读，
但无可信宿主绑定的项目调用会明确拒绝，不再选择最近会话。

`MRW_SKILL_SOURCE_ROOT` 指向宿主实际可读的后端 skills 根（默认主仓
`main/backend/skills`）。容器返回的技能相对路径在该根解析并核对正文摘要；
容器绝对路径不直接作为宿主挂载路径。注册、项目激活、宿主挂载及业务执行分别读回，
历史未核验包不自动变成可信安装。

### Codex WebUI 生命周期

当前服务来自 [vendored README](./codex-webui/README.md) 所描述的主仓副本，运行主程序为
`main/ops/codex-webui/dist/main.js`，协议依赖固定为 `@openai/codex@0.160.0`。原 SQLite
数据已完整迁入 `main/ops/codex-webui/.tmp`；宿主 LaunchAgent 指向主仓路径，
`com.mrw.codex-webui` 的认证 symlink 仍共享宿主 `~/.codex/auth.json`。

启动时由已有私密配置提供 `WEBUI_API_KEY`；不要打印、记录或提交该密钥：

```bash
./main/ops/codex-webui/start.sh
```

停止同一 LaunchAgent：

```bash
./main/ops/codex-webui/stop.sh
```

构建、版本校验、认证 symlink、数据库路径和 LaunchAgent 生成的完整说明见
[`./codex-webui/README.md`](./codex-webui/README.md)。

本机状态与健康检查：

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
```

分面控制使用既有入口：

```bash
./scripts/local-service-control.sh frontend-start
./scripts/local-service-control.sh worker-start
./scripts/local-service-control.sh backend-start
```

## Compose 隔离本地用户环境（2026-09-21）

这个模式用于容器边界下的本地用户验证，不是当前宿主 daily 默认叙述。本机可使用此前
生产部署验证保留的 backend 镜像与当前源码只读挂载启动用户界面，无需重建镜像。
这不是冻结候选的 exact-byte replay，也不是生产部署。Compose project 固定为
`mrw-local-user`；数据保存在该 project 的独立命名卷中，不使用宿主 PostgreSQL/Redis。

在仓库根目录执行：

```bash
# 首次启动或前端修改后构建；纯重启无需重复。
npm --prefix main/frontend-modern run build

docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  --profile modern-ui up -d --no-build --pull never \
  db es redis backend celery-worker frontend-modern
```

界面为 <http://127.0.0.1:15132/>，API 为 <http://127.0.0.1:18132/docs>，仅绑定 loopback。
只有列出的六个服务被启动，不包含 launcher、scrapyd 或搜索增强服务。
Compose 挂载默认使用 sibling `Desktop/functorial-kit/python`；可用
`MRW_FUNCTORIAL_KIT_PATH` 指定其他已有 checkout。当前源码需要其中的
`functorial_kit.contributions`，保留镜像自带旧 wheel 不具备此模块。
backend 同时挂载当前 `app`、`migrations`、`llm_prompts`、`src` 与 `seed_data`；
worker 使用同一 `app/src/kit`，前端使用当前 `dist`。修改普通 API Python 后重启 backend；修改 Celery task 定义或注册时重启 backend 和 `celery-worker`，避免 worker 保留旧注册清单：

```bash
docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  restart backend celery-worker
```

此配置不读取宿主 `.env`，不注入 provider key 或 Codex 登录文件。默认 dev 模式没有普通账号登录要求；
Codex OAuth、模型、外部检索与网页采集未验证。不要把页面显示的 `missing/login` 当成已配置。

停止并保留所有本地数据：

```bash
docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  --profile modern-ui stop db es redis backend celery-worker frontend-modern
```

重新执行上述 `up` 恢复。不要使用 `down -v` 或全局 prune。日志可从
`docker compose` 同样参数的 `logs backend celery-worker` 读取，worker 文件日志也由任务详情页读取。

已注入的演示项目是 `local_demo_20260921`：通过产品 `POST /api/v1/projects/inject-initial`
从 `seed_data/project_demo_proj_v0.9-rc2.0.sql` 复制 75 条文档、6 条来源；`overwrite=false`，
没有复制 seed 内的历史 ETL 任务。当前 URL 池的 267 条链接由本次页面“提取 URL”提交的真实
Celery 任务产生。用户操作：项目管理切换该项目 → 管理/提取 → 提取 URL → 任务详情查看
`SUCCESS` 与 result → 返回提取页刷新列表。提取仅扫描已入库文档，不访问链接目标。
重复提取使用已有去重逻辑，不重复新增相同链接。

原始数据导入接口的 `async_mode=true` 使用 Celery task
`app.services.tasks.task_raw_import_documents`；可通过 Process 详情读回任务结果，再从文档列表检索新记录。2026-09-21 的有界验证及回执位于下方运行记录目录。

本次运行证据：[`local-user-chain/2026-09-21`](../../development/latest-dev-docs/automation-runs/local-user-chain/2026-09-21/)。
此前生产部署的历史验收结果保持原义；本环境不延续那轮已停止的执行，也不授予发布权限。

## Docker 应用栈

完整容器应用栈与上述隔离环境是不同运行模式。仓库根入口直接转发到现有 Compose 控制脚本：

```bash
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh start --profile modern-ui
./scripts/docker-deploy.sh status
./scripts/docker-deploy.sh health
./scripts/docker-deploy.sh logs
./scripts/docker-deploy.sh stop --profile modern-ui
```

macOS 桌面入口 `./scripts/platform-macos.sh docker-app-start` 启动同一完整应用栈；
`docker-start` 只打开 Docker 控制台。外部服务配置使用
`python3 scripts/launch.py` 或 `./scripts/platform-macos.sh configure`。
检查点、回滚和 fixture-only dry-run 的当前参数以
`./scripts/docker-deploy.sh --help` 与 `./main/ops/rollback.sh --help` 为准。

## Concept Workbench overlay

`main/ops/docker-compose.workbench.yml` 是完整 Compose 应用栈的可选 backend overlay。
它要求调用者显式提供现有 Workbench checkout 和项目绑定，不从固定个人路径或最近项目推断：

```bash
export MRW_CONCEPT_WORKBENCH_SOURCE="/absolute/path/to/concept-architecture-workbench"
export MRW_WORKBENCH_TARGETS='{"mrw":{"root":"/workspace/mrw","project_key":"hk_water_investigation","label":"MRW"}}'
docker compose \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.workbench.yml \
  up -d --no-deps --no-build backend
```

该 overlay 只挂载 Workbench SDK 和具名项目目标；真实工具执行仍沿现有可信宿主、项目权限和业务 writer。
