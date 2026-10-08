# 开发指南

项目修改从当前源码、原生声明和相关测试出发。运行步骤见[使用说明](../usage.md)，模块与事实归属见[架构说明](../architecture/README.md)。

文档规划的全部有限精简面已完成本地验收，具体处置、具名保留核、成本和证据见[阶段§5–7](MRW平台结构精简与删减阶段.md#5-持续推进与分层退出)。本波从`cc1ea6c1`使app Python净减3247行，由641文件231238行降至632文件227991行；从`a17930da`累计净减71243行（23.81%）。K最终净增304、L净增12及其它预算偏差保留，测试、工具、JSON、前端和文档另账。

上轮八切口已提交至`ee20e32d`，app Python净减583行至231118行；backend2505项及root1350项实际通过，4项原skip。完整成本、coverage和真实读回见[阶段§4历史结果](MRW平台结构精简与删减阶段.md#4-有限删除波次与待重构组合)，这些结果只作为本轮基线。

总体设计见[MRW精简框架](MRW精简框架.md)，当前剩余实现合同见[阶段§5](MRW平台结构精简与删减阶段.md#5-持续推进与分层退出)，已完成批次及原证据见阶段§4。已提交基线`2f20e9f`中，从`a17930da`实施的有限删除波次及修复使app Python由299234减至231701行，净减67533行（22.57%）；JSON、前端、kit、工具与测试另账，首两批历史保持在阶段§2.1/§2.2。

更早2444项清单、分步kept与历史live结果只作基线，保留于阶段§4。四项产品接缝已按该节独立状态与证据收口；当前剩余包须读回各自新验证，避免将旧通过记录当作新验证。

最终backend collection3757、root1342由原全集执行、精确失败修复和本地PG补跑闭合，未声称一次全部重跑；当前coverage core100%/other67.12%，公共类型0/0、sync/check clean、七gate234通过。K真实PG45、L真实PG5及Ops mock Playwright11分别保留证明范围。两个外部live链未执行，两个静态negative由Pyright预期失败承担；旧失败attempt不改为PASS，内部类型债不追加为新治理项目。必要领域writer、Runtime事实owner、权限/UNKNOWN及具名provider/恢复核保持。未push/deploy，旧Stage4–6继续STOPPED；[原结构整理方案](MRW结构整理方案与分发包.md)只作历史。

2026-10-09追加的安装边界与选定内部类型质量修复已完成本地有界验证，见[阶段修复记录](MRW平台结构精简与删减阶段.md#安装边界与选定内部类型修复2026-10-09)。本轮从`c2a86b60`的632文件227991行变为632文件228755行，净增764行；七factory合并与旧反向forwarder退出的结构收益独立记录，名称搬迁收益为0。公共及明确扩入的strict边界0错误、选定pure254与真实PG36、七gate235实际通过；完整collection不等于全量执行，不宣称全仓内部类型清零。四个`FirstSpecimen` wire异常名保留；上轮有限精简完成事实、冻结历史及未push/deploy边界保持。

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
