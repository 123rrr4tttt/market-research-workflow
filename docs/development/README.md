# 开发指南

项目修改从当前源码、原生声明和相关测试出发。运行步骤见[使用说明](../usage.md)，模块与事实归属见[架构说明](../architecture/README.md)。

总体设计见[MRW 精简框架](MRW精简框架.md)；首个大阶段单独见[平台结构精简与删减阶段](MRW平台结构精简与删减阶段.md)。两者已完成主线审查，首阶段已获授权实施，正在先行收缩；实际包状态与验证结果在阶段文件维护。

阶段文件统一维护目标、保留承载、删除族、独占写面、依赖、串并行安排、验证资源与退出条件，以消费者切换、旧职责同批删除及生产源码和维护结构净下降结束。全面类型强化、UI重设计、性能优化和新扩展设施等后置，删除必需的最小修改除外。[原结构整理方案](MRW结构整理方案与分发包.md)保留历史证据，旧终点计数和分包不驱动当前安排。

## 找到修改位置

| 需求 | 入口 |
| --- | --- |
| API、领域服务和持久化 | [后端文档](../../main/backend/docs/README.md)与 `main/backend/app` |
| 业务界面 | [前端说明](../../main/frontend-modern/README.md) |
| Codex WebUI 与运行配置 | [WebUI 说明](../../main/ops/codex-webui/README.md)、[运维说明](../../main/ops/README.md) |
| 新能力声明与装配 | [contributions](../../contributions)、[贡献目录](../../contributions/project_catalog.py)、[开发入口](../../scripts/dev.py) |
| 历史方案和验收记录 | [历史资料](../history/README.md) |

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

## 维护规则

每项语义事实有唯一声明位置；注册、接线和投影沿已有贡献入口派生。直接修复，做最小相关验证，批次稳定后按实际交付需要封存。保留其他作者改动和历史证据。

完整工程约定见 [AGENTS.md](../../AGENTS.md)。流程缩减规则继续由[既有规则文档](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/19_direct-testing-batch-freeze-amendment.v1.md)维护。

## 旧文档入口

已完成清简与修复方案从[历史资料](../history/README.md)查阅。[计划历史](development-plans/README.md)、[前端历史](frontend-modern/README.md)和[根计划历史](root-plans/README.md)保留专题导航。

历史迁移的派生清单为 [latest-dev-docs-entry-manifest.json](latest-dev-docs-entry-manifest.json) 和 [latest-dev-docs-content-plan.json](latest-dev-docs-content-plan.json)，迁移证据集中在[文档迁移记录](../history/documentation-migration.md)。其一致性由 [scripts/checkers/check_docs_root_content_plan.py](../../scripts/checkers/check_docs_root_content_plan.py)检查。
