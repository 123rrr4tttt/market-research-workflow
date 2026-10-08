# 开发指南

项目修改从当前源码、原生声明和相关测试出发。运行步骤见[使用说明](../usage.md)，模块与事实归属见[架构说明](../architecture/README.md)。

当前从干净`main@ee20e32d`收口四项遗留接缝：首次Runtime provisioning、宿主重复只读观察、demo检索配置和本机父iframe认证连续性。四项原消费者已实际读回，公共门禁242项通过；app必要收口成本净增120行，JSON、CLI与测试另账。独占写面、依赖及原验证入口见[阶段§4](MRW平台结构精简与删减阶段.md#四项遗留接缝的有限收口2026-10-08)。

上轮八切口已提交至`ee20e32d`，app Python净减583行至231118行；backend2505项及root1350项实际通过，4项原skip。完整成本、coverage和真实读回见[阶段§4历史结果](MRW平台结构精简与删减阶段.md#4-有限删除波次与待重构组合)，这些结果只作为本轮基线。

总体设计见[MRW精简框架](MRW精简框架.md)，当前结果及剩余切口见[阶段§4](MRW平台结构精简与删减阶段.md#4-有限删除波次与待重构组合)。已提交基线`2f20e9f`中，从`a17930da`实施的有限删除波次及修复使app Python由299234减至231701行，净减67533行（22.57%）；JSON、前端、kit、工具与测试另账，首两批历史保持在阶段§2.1/§2.2。

更早2444项清单、分步kept与历史live结果只作基线，保留于阶段§4。当前四项收口按该节独立状态与证据读回，避免将旧通过记录当作新验证。

此前删除与九项能力覆盖不等于整体架构重构完成。source resolver/runner、Agent URL提交、search matrix、discovery/clue组合、旧tool协议桥等八个切口已按上轮合同实施并取得局部见证，中央结果见阶段§4。具名保留核与其他未进入已验收闭包的组织仍分别承担后续判断，不能把整handler包装或搬家叫特殊核保留；生产入口、原装配、旧闭包删除和权限/失败保持继续按真实证据确定，不新建Runtime或大框架。旧部署Stage4–6继续STOPPED，未push或deploy；[原结构整理方案](MRW结构整理方案与分发包.md)只作历史。

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
