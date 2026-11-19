# 开发指南

项目修改从当前源码、原生声明和相关测试出发。运行步骤见[使用说明](../usage.md)，模块与事实归属见[架构说明](../architecture/README.md)。

## 找到修改位置

| 需求 | 入口 |
| --- | --- |
| API、领域服务和持久化 | [后端文档](../../main/backend/docs/README.md)与 `main/backend/app` |
| 业务界面 | [前端说明](../../main/frontend-modern/README.md) |
| Codex WebUI 与运行配置 | [WebUI 说明](../../main/ops/codex-webui/README.md)、[运维说明](../../main/ops/README.md) |
| 新能力声明与装配 | [contributions](../../contributions)、[贡献目录](../../contributions/project_catalog.py)、[开发入口](../../scripts/dev.py) |

## 贡献检查

从仓库根目录执行。默认使用 `main/backend/.venv311`，可用 `MRW_DEV_PYTHON` 指定等价环境。kit 的依赖来源固定在 [pyproject.toml](../../pyproject.toml)；已有环境先运行 `check`，需要安装时才显式运行 `setup`。

```bash
python3 scripts/dev.py check
python3 scripts/dev.py sync
python3 scripts/dev.py test
python3 scripts/dev.py gates
```

`check` 核验依赖来源和贡献状态；`sync` 更新派生投影；`test` 执行贡献相关测试；`gates` 执行架构门禁。`validate` 是既有组合检查，`inspect` 提供词法导航和显式依赖信息。

```bash
python3 scripts/dev.py setup
python3 scripts/dev.py validate
python3 scripts/dev.py inspect
```

使用本地 kit 时，各命令追加 `--local-kit <checkout>/python`；该路径须为真实 Git checkout 的 Python 包目录，并先通过 `setup --local-kit` 显式安装。

## 相关验证

按受影响行为选择已有测试，后端统一入口为：

```bash
./scripts/test-standardize.sh unit
./scripts/test-standardize.sh integration
./scripts/test-standardize.sh contract
./scripts/test-standardize.sh ci-pr
```

前端命令见[前端说明](../../main/frontend-modern/README.md)。需要数据库、端口或外部服务的测试须使用声明的隔离资源；只在真实集成或交付要求时运行完整套件。

## 贡献与维护边界

每项领域语义、效果与事实由既有执行者拥有。模块作为承担特定信息处理职责的局部整体，通过[原生贡献目录](../../contributions/project_catalog.py)提供声明，并由现有装配接入真实消费者；不要求模块有独立进程、数据存储或页面。跨领域的工具和视图沿原定义派生，不另建一份登记和写入合同。涉及 Agent 能力，沿现有 Cell 接线，不从业务服务直接接 provider。

从受影响的原定义、代码和消费者出发，选最小相关验证。显示一项能力、检查装配、在集成测试中通过、真实效果可读回，是不同层面的结论。协作规则见 [AGENTS.md](../../AGENTS.md)。
