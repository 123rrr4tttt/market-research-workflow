# 市场研究工作流

> 最后更新：2026-10-05
> 当前状态：本机日常链路可用；生产部署历史已停止，发布延后且未建立生产授权
> 开发阅读唯一入口：[`docs/development/README.md`](./docs/development/README.md)

这是一个面向市场研究、来源采集、结构化分析和报告生成的本地工作流仓库。核心能力覆盖项目管理、文档导入、来源库、采集任务、索引与检索、图谱、写作、Agent 运行和任务运维；前后端放在同一工程内，便于把一次研究请求从界面操作追溯到 API、后台任务、索引和持久读回结果。

## 先读入口

日常使用和开发阅读从 [`docs/development/README.md`](./docs/development/README.md) 进入。它直接分流三类事实：

1. 本机 daily 运行：当前可用的界面、API、任务 worker、搜索依赖和业务操作。
2. 已停止的生产部署历史：2026-09-13 的本地验收、清理完成、停止执行和发布延后记录。
3. 开发计划与历史档案：当前计划、已关闭主题、外部阻塞和兼容路径。

本 README 是使用与运行入口，不承担开发文档索引。历史文件、旧路径和冻结证据保持原位；旧链接仍应可达。

## 本机日常链路

2026-10-04 的完整日常链路证据在 [`.data/readiness-repair/20261004-daily-chain/daily-chain-state.json`](./.data/readiness-repair/20261004-daily-chain/daily-chain-state.json)，状态为 `LOCAL_DAILY_FULL_CHAIN_VERIFIED`。该证据记录了策略文档导入、解析、索引、词法和 pgvector 检索、HTTP 来源修复、原生 Codex 任务完成，以及队列清空、worker 响应和健康检查通过。

| 运行面 | 地址或身份 | 说明 |
| --- | --- | --- |
| 业务前端 | <http://127.0.0.1:5173> | 市场研究工作流的日常操作界面 |
| 后端 API | <http://127.0.0.1:8000/docs> | OpenAPI 文档和业务 API |
| Codex WebUI | <http://127.0.0.1:8172>，MRW 路由 `/codex/` | 主仓 vendored 入口，启动标签为 `com.mrw.codex-webui`；见 [vendored README](./main/ops/codex-webui/README.md) |
| Celery worker | `com.mrw.local-worker` | launchd 管理的正式本地后台任务进程 |
| Elasticsearch | `com.mrw.local-elasticsearch` | launchd 管理的本机搜索依赖 |
| OAuth 身份 | 宿主 `~/.codex/auth.json` | Codex WebUI 通过宿主共享身份；`~/.codex-mrw-agent` 为其 home，并建立共享 symlink |

日常状态与健康检查可用：

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
```

需要单独控制本机运行面时，使用既有控制脚本；这些命令按进程或 launchd 表面操作：

```bash
./scripts/local-service-control.sh frontend-start
./scripts/local-service-control.sh frontend-stop
./scripts/local-service-control.sh worker-start
./scripts/local-service-control.sh worker-stop
./scripts/local-service-control.sh backend-start
./scripts/local-service-control.sh backend-stop
```

日常证据中的验证边界也应保留：pgvector 后端已验证；旧 Qdrant 数据迁移未完成；HK 历史材料不可用。2026-10-04 daily-chain 证据生成时，WebUI 仍运行外部工作树源；该源现已归入主仓，当前启动方式见下节。页面显示的 `missing/login` 不能当作已配置，模型、外部检索或网页采集是否可用要按具体操作读回判断。

### Codex WebUI 启动与停止

Codex WebUI 使用 [main/ops/codex-webui](./main/ops/codex-webui) 中的 vendored 源码和 `dist/main.js`，协议依赖固定为 `@openai/codex@0.160.0`。原 SQLite 运行数据已完整迁入主仓忽略目录 `.tmp`；宿主 LaunchAgent 使用主仓路径，`~/.codex-mrw-agent/auth.json` 继续以 symlink 共享宿主 `~/.codex/auth.json`。

启动由已有私密配置向进程提供 `WEBUI_API_KEY`；不要在命令历史、日志或文档中打印这个密钥：

```bash
./main/ops/codex-webui/start.sh
```

停止只卸载同一个 LaunchAgent：

```bash
./main/ops/codex-webui/stop.sh
```

构建、版本校验、认证 symlink、数据库路径和 LaunchAgent 生成的完整说明见 [main/ops/codex-webui/README.md](./main/ops/codex-webui/README.md)。

## 业务能力

- **项目管理**：创建、切换和注入演示项目；项目边界贯穿文档、任务、检索和报告。
- **来源库**：登记来源、解析内容、维护项目定制来源，并把可复用来源接到采集和检索。
- **采集与导入**：支持文件导入和 HTTP 来源获取；异步任务由 Celery 执行，Process 页可读回任务状态和结果。
- **索引与检索**：文档进入 Elasticsearch、BM25 和 PostgreSQL vector 索引；按项目隔离检索候选和结果。
- **图谱与知识组织**：维护实体、关系、类型化知识和工作流图，为分析和写作提供结构化上下文。
- **写作与报告**：把项目材料、检索结果和任务证据汇入写作流程，生成可审查报告。
- **Agent 与任务运维**：前端展示任务、日志、worker 事件和失败原因；后端暴露健康检查和运维 API。

这些能力的实现集中在 `main/backend/app/services`，界面在 `main/frontend-modern`。目录名只帮助定位源码；使用入口按上面的业务语义理解。

## 项目贡献检查

本地贡献开发入口默认使用 `main/backend/.venv311`，也可用 `MRW_DEV_PYTHON` 指向等价 Python 环境。默认 kit 来源由 [`pyproject.toml`](./pyproject.toml) 的 `[tool.mrw.dev-kit]` 固定为 functorial-kit Git revision `6dbae536a72ab235998b21c9647b8b00d15a71e6` 的 `python` 子目录：

```bash
python3 scripts/dev.py setup
python3 scripts/dev.py check
python3 scripts/dev.py sync
python3 scripts/dev.py inspect
python3 scripts/dev.py test
python3 scripts/dev.py gates
python3 scripts/dev.py validate
```

`setup` 是显式安装入口，安装后回验 kit 来源；`check` 只核验当前安装来源和贡献状态，不安装。`sync` 执行既有贡献投影同步；`test` 和 `validate` 需要所选环境已有 SQLAlchemy 等后端测试依赖；`inspect` 返回词法导航候选和显式依赖关系，不能直接当作受影响测试选择器。

同一组子命令可追加 `--local-kit <checkout>/python` 使用显式本地 kit。该路径必须是真实 functorial-kit Git checkout 的 `python` 包目录；先用 `setup --local-kit` 安装为 editable，之后其他子命令只核验安装确实来自同一路径，不隐式安装：

```bash
python3 scripts/dev.py setup --local-kit /path/to/functorial-kit/python
python3 scripts/dev.py check --local-kit /path/to/functorial-kit/python
```

后端常用测试仍按层级选择：

```bash
cd main/backend
pytest -m "unit and not external and not flaky" -q
pytest -m "integration and not external and not flaky" -q
pytest -m "contract and not external and not flaky" -q
```

仓库脚本也保留统一入口：

```bash
./scripts/test-standardize.sh unit
./scripts/test-standardize.sh integration
./scripts/test-standardize.sh contract
./scripts/test-standardize.sh ci-pr
```

## 本机日常与容器模式

当前默认叙述是本机 daily：5173 的业务前端、8000 的 API、8172 的 Codex WebUI，加上 launchd 管理的 worker 和搜索依赖。它服务于当前机器上的实际研究和开发。

Compose 隔离模式用于本地用户环境验证或需要容器边界的运行。它的数据归独立 Compose project，不使用宿主 PostgreSQL/Redis。端口和命令以 [`main/ops/README.md`](./main/ops/README.md) 为准；该说明区分宿主日常和 Compose 隔离，不把隔离结果当作生产部署。

启动 Docker 控制台的既有命令仍有效，但它只启动控制台：

```bash
./scripts/platform-macos.sh docker-start
```

| 入口/模式 | 负责对象 | 启动命令 | 访问地址 | 停止范围 |
| --- | --- | --- | --- | --- |
| 本机 daily | 本机 backend、Vite frontend、launchd worker | `./scripts/local-service-control.sh` 分面控制 | 前端 5173，API 8000 | 指定本机进程/launchd 表面 |
| Docker 控制台 | launcher-agent 和 launcher-ui 控制面 | `./scripts/platform-macos.sh docker-start` | 控制台 5176 | 控制台容器 |
| Docker 应用栈 | db、es、redis、backend、worker、frontend | 控制台 Start，或 `./scripts/platform-macos.sh docker-app-start` | 前端 5174，API 8000 | Docker 应用服务 |
| Compose local-user | 六个隔离服务 | 见 [`main/ops/README.md`](./main/ops/README.md) | 15132/18132 | 指定 Compose project |

`docker-start` 只打开控制台，不代表业务栈已启动。控制台显示 `App 6/6` 后，业务前端才可用。

## 目录与运行来源

| 路径 | 作用 |
| --- | --- |
| `main/backend` | FastAPI、服务层、Celery 任务、迁移和后端测试 |
| `main/frontend-modern` | 当前业务前端 |
| `main/ops` | 容器编排、启停脚本和运维说明 |
| `scripts` | 仓库级启动、检查、测试和维护脚本 |
| `docs/development` | 当前开发阅读根、历史计划与归档 |
| `.data/readiness-repair/20261004-daily-chain` | 当前 daily 全链路证据 |

来源库运行配置和历史导入材料可能在中文目录中保存；定位时以实际链接和源码配置为准，不要把参考目录当作运行时。

## 生产历史边界

生产部署阶段已于 2026-09-13 完成本地验收和验收后清理，随后停止；正式发布延后，未建立生产授权。当前 README 的命令只用于本机日常、贡献检查和容器隔离验证。历史验收、冻结证据和阶段记录不改写、不迁移；需要追溯时从 [`docs/development/README.md`](./docs/development/README.md) 的生产历史入口进入。

## 协作

- 工程规则入口：[`AGENTS.md`](./AGENTS.md)
- Git 约定：[`GIT_WORKFLOW.md`](./GIT_WORKFLOW.md)
- 开发阅读：[`docs/development/README.md`](./docs/development/README.md)
- 运行与隔离模式：[`main/ops/README.md`](./main/ops/README.md)
