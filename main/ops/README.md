# 本地与容器运行入口

## 本机日常运行

当前宿主日常链路由业务前端、后端 API、Codex WebUI、launchd 管理的 Celery worker 和
Elasticsearch 组成。访问地址为前端 <http://127.0.0.1:5173>、API
<http://127.0.0.1:8000/docs>、Codex WebUI <http://127.0.0.1:8172>。OAuth 身份由宿主
`~/.codex/auth.json` 共享给 WebUI；WebUI home 是 `~/.codex-mrw-agent`，并通过共享
symlink 读取宿主身份。首次配置与启动见[本机使用说明](../../docs/usage.md#首次运行)。

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
只使用可核验的技能包。

### Codex WebUI 生命周期

WebUI 的构建、协议版本、线程数据和认证配置见[服务说明](./codex-webui/README.md)。

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

业务界面的「后端 → 运行健康」读取当前深度健康接口，显示数据库、连接池和 Elasticsearch 的检查结果。它不验证 worker 是否实际消费任务；队列是否可用请以任务页的执行结果为准。

分面控制使用既有入口：

```bash
./scripts/local-service-control.sh frontend-start
./scripts/local-service-control.sh worker-start
./scripts/local-service-control.sh backend-start
```

## Compose 隔离验证

此模式用于容器边界下的本机验证，不是本机工作台的首跑路径。它从当前源码构建后端、worker 与前端镜像，需要 Docker and Compose。Compose project 为 `mrw-local-user`，使用隔离的命名卷，不使用宿主 PostgreSQL 或 Redis。

在仓库根目录执行：

```bash
docker compose -p mrw-local-user \
  -f main/ops/docker-compose.yml -f main/ops/docker-compose.local-user.yml \
  --profile modern-ui up -d --build --pull never \
  db es redis backend celery-worker frontend-modern
```

界面为 <http://127.0.0.1:15132/>，API 为 <http://127.0.0.1:18132/docs>，仅绑定 loopback。
只有列出的六个服务被启动，不包含 launcher、scrapyd 或搜索增强服务。
镜像直接由当前源码构建，不依赖预载的历史镜像或兄弟 checkout。修改源码后重新执行同一 `up --build` 命令；只重启现有容器不会包含源码修改：

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
