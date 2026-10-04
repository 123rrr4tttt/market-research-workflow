# 使用说明

以下命令从仓库根目录执行。当前本机日常模式由业务前端、API、任务 worker、搜索依赖和 Codex WebUI 组成。

## 日常操作

1. 在业务界面创建或选择项目，让来源、文档、检索和报告落在同一项目范围内。
2. 导入文件或采集来源，在任务页面查看解析、索引和失败原因。
3. 按项目检索材料，通过图谱或写作工作台组织结果。
4. 需要 Agent 时进入 Codex WebUI；任务是否完成以执行结果和持久读回为准。

| 服务 | 默认入口 |
| --- | --- |
| 业务界面 | <http://127.0.0.1:5173> |
| 后端 API | <http://127.0.0.1:8000/docs> |
| Codex WebUI | <http://127.0.0.1:8172>；业务界面代理路由 `/codex/` |

## 查看状态与启停

```bash
./scripts/local-deploy.sh status
./scripts/local-deploy.sh health
```

按需启动或停止本机进程：

```bash
./scripts/local-service-control.sh backend-start
./scripts/local-service-control.sh worker-start
./scripts/local-service-control.sh frontend-start

./scripts/local-service-control.sh frontend-stop
./scripts/local-service-control.sh worker-stop
./scripts/local-service-control.sh backend-stop
```

Codex WebUI 单独管理：

```bash
./main/ops/codex-webui/start.sh
./main/ops/codex-webui/stop.sh
```

WebUI 的构建、版本、数据库位置及 LaunchAgent 配置统一见[服务说明](../main/ops/codex-webui/README.md)。worker 与 Elasticsearch 的本机服务标签分别为 `com.mrw.local-worker`、`com.mrw.local-elasticsearch`。

## 认证

Codex WebUI 共享宿主 `~/.codex/auth.json` 的 OAuth 身份；服务 home 为 `~/.codex-mrw-agent`，其中的认证文件以符号链接指向宿主身份。宿主尚未登录时，先完成宿主 Codex 登录，再启动 WebUI。

WebUI API 密钥由已有私密配置提供。启动脚本会验证配置、固定 Codex CLI 版本和认证链接；出现错误时按错误文字处理，不在文档或日志中记录凭据。

## 容器运行

容器模式的具体命令、隔离数据和端口统一见[运维说明](../main/ops/README.md)。

| 模式 | 入口 | 默认端口 |
| --- | --- | --- |
| Docker 控制台 | `./scripts/platform-macos.sh docker-start` | 控制台 5176 |
| Docker 应用栈 | 控制台 Start 或 `./scripts/platform-macos.sh docker-app-start` | 前端 5174，API 8000 |
| Compose 隔离验证 | 按运维说明使用独立 Compose project | 前端 15132，API 18132 |

控制台启动后需要启动应用栈；显示 `App 6/6` 后再访问业务界面。宿主和 Docker 应用栈默认都使用 API 8000，切换模式前确认端口所属进程。

## 运行记录与边界

2026-10-04 本机整链记录：[daily-chain-state.json](../.data/readiness-repair/20261004-daily-chain/daily-chain-state.json)，状态为 `LOCAL_DAILY_FULL_CHAIN_VERIFIED`。记录覆盖文档导入、解析、索引、词法与 pgvector 检索、HTTP 来源、Codex 任务及 worker 读回；它是该次运行记录，当前状态用上面的命令检查。

当时 WebUI 运行来源仍是外部工作树，之后已归入主仓；当前启动来源以服务说明为准。旧 Qdrant 数据迁移和 HK 历史材料缺口保留；外部模型、检索或采集能否使用须按具体操作确认。本机验证与已停止的发布历史分别记录，历史资料见[历史入口](history/README.md)。
