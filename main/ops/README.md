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
宿主 API。Docker 与宿主是不同实例，不能凭相同 `project_key` 混用资料；不要把 Docker 业务页能打开宿主 WebUI 当作接线成功。

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

## 完整本机 Docker 部署

完整单用户工作台的 Docker 入口是仓库根目录的：

```bash
./scripts/local-docker-deploy.sh up
```

它读取私密文件 `main/ops/.env.local-user`，使用 Compose project `mrw-local-user`，构建业务界面、API、worker 和 Codex WebUI，启动独立 PostgreSQL、Redis、Elasticsearch，并等待业务与 WebUI 健康。默认业务界面为 <http://127.0.0.1:15132>，API 为 <http://127.0.0.1:18132/docs>。配置模板见 [`.env.local-user.example`](.env.local-user.example)，使用说明见[本机 Docker 部署](../../docs/usage.md#本机-docker-部署)。

```bash
./scripts/local-docker-deploy.sh status
./scripts/local-docker-deploy.sh health
./scripts/local-docker-deploy.sh logs
./scripts/local-docker-deploy.sh down
```

`down` 保留命名卷；`reset` 才会删除业务数据库、搜索索引、Redis 数据、worker 日志以及包含 WebUI SQLite、线程文件和 Codex 登录状态的卷。Compose project 和卷必须与另一个 checkout 隔离。不要用宿主 `.env`、宿主 PostgreSQL、宿主 Redis、宿主 Elasticsearch 或宿主 Codex 登录替代容器内的实例。

## Docker 应用栈

下面是一般开发与运维入口，不是完整单用户 Docker 安装的验收路径。仓库根入口转发到现有 Compose 控制脚本：

```bash
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh start --profile modern-ui
./scripts/docker-deploy.sh status
./scripts/docker-deploy.sh health
./scripts/docker-deploy.sh logs
./scripts/docker-deploy.sh stop --profile modern-ui
```

macOS 桌面入口 `./scripts/platform-macos.sh docker-app-start` 启动这套应用栈；
`docker-start` 只打开 Docker 控制台。外部服务配置使用
`python3 scripts/launch.py` 或 `./scripts/platform-macos.sh configure`。
检查点、回滚和 fixture-only dry-run 的当前参数以
`./scripts/docker-deploy.sh --help` 与 `./main/ops/rollback.sh --help` 为准。

## 服务器部署参考（非本机安装）

这是服务器配置的维护参考，不是单用户工作台的安装方式，也不属于本次交付验收。生产容器配置使用独立的 [生产 Compose](docker-compose.production.yml)，不与本机或开发 Compose 叠加。先运行与 CI 同源的两项检查：

```bash
python3 scripts/formal_release/check_static_production_contract.py
python3 scripts/formal_release/check_production_compose_config.py
```

前者需要 Python 环境中已安装 `packaging`，检查发布版本、配置结构和仓库门禁声明；后者用合成输入只渲染，既不拉取镜像也不启动服务。两项通过不代表镜像、迁移、认证或业务链路已验收。

有获准的目标环境后，从 [生产环境模板](../backend/.env.production.example) 在仓库外准备私密 env 文件；凭据不进 Git、不进镜像。使用真实镜像摘要、构建标识和运行策略，只返回检查状态，不输出渲染后的配置：

```bash
docker compose -f main/ops/docker-compose.production.yml \
  --env-file "$MRW_PRODUCTION_ENV_FILE" config --quiet
```

执行前确保当前 shell 没有同名变量覆盖该文件。真实上线还需在目标环境独立验证镜像、迁移和回滚、API/worker，以及经 Cell 的实际调用与持久读回；不要用本机或历史记录替代。

## PostgreSQL 备份与恢复演练

在已确认的 MRW 源数据库备份完整数据库，不只导出 `public`：项目数据和工作流记录还在各项目的 schema 中。
用隔离的恢复环境和**新建空库**演练，不覆盖现用数据库。目标 PostgreSQL 需备好与源库相容的版本、
`vector` 扩展及恢复所需的数据库角色；连接和凭据使用运维已有的私密配置，不写入仓库或日志。

```bash
# PGHOST / PGPORT / PGUSER 指向源 PostgreSQL；SOURCE_DB 指定 MRW 源数据库。
# BACKUP_DIR 是已创建的私有目录；每次演练用新的目录和目标数据库名。
(
  set -eu
  umask 077
  cd "${BACKUP_DIR:?}"
  pg_dump --format=custom --file=mrw.dump "${SOURCE_DB:?}"
  shasum -a 256 mrw.dump > mrw.dump.sha256
  shasum -a 256 -c mrw.dump.sha256
  pg_restore --list mrw.dump > mrw.dump.list

  # RESTORE_PGHOST / RESTORE_PGPORT / RESTORE_PGUSER 指向隔离目标。
  export PGHOST="${RESTORE_PGHOST:?}" PGPORT="${RESTORE_PGPORT:?}" PGUSER="${RESTORE_PGUSER:?}"
  createdb --template=template0 "${RESTORE_DB:?}"
  pg_restore --single-transaction --exit-on-error --dbname="$RESTORE_DB" mrw.dump
  psql -X -v ON_ERROR_STOP=1 -d "$RESTORE_DB" -c 'TABLE public.alembic_version;'
)
```

命令成功只表示数据库已恢复。用与备份版本相符的独立 API 实例连接恢复库，比较恢复前后同一项目下
的材料正文及来源、写作文档与引用、类型化知识，以及已完成的工作流及其事件；用另一已安装 Runtime
的项目检查读不到原项目的样本，并检查工作流在未认证时被拒绝。普通业务项目创建不是 Runtime 授权；
若演练需要先在新项目里执行工作流，运维通过 `main/backend/scripts/provision_project_runtime.py` 显式安装
项目 Runtime，按实际批准配置目标 actor、唯一 incarnation、允许的操作与资源上限及有限期 grant。

此流程不恢复外部文件、Codex WebUI 独立数据卷、搜索索引或 Redis 在途任务。演练的 API 和 worker
不得连到生产队列或外部执行入口；恢复演练通过也不表示可以接管生产流量。

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
