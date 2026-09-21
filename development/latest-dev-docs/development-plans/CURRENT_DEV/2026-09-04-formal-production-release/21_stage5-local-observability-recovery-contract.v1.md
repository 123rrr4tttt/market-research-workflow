# Stage 5：本地可观测性与恢复执行合同

- Date: 2026-09-13
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Executor: `01a099f6-8ee3-7371-8e3b-91b8ebebac79`
- Status: `DISPATCHED_LOCAL_STAGE5`
- Scope: `LOCAL_STAGE5_ONLY / NOT_AUTHORITY / RELEASE_DEFERRED`

## 1. 准入与输入

Stage 4 已经监督审核为 `PASS_LOCAL_STAGE4_NOT_AUTHORITY`。读取项目 AGENTS、[19 流程规则](19_direct-testing-batch-freeze-amendment.v1.md)、[06 当前进度](06_production-deployment-stage-progress.v1.md)及本合同。实际输入引用 [Stage 4 主结果](stage4-evidence/stage4-stage-result.json)、[运行说明](stage4-evidence/RUNBOOK.md)、[最终构建映射](stage4-evidence/runtime/c9-effect-build.json)和 runtime/SHA256SUMS；以最终 C9 backend/Celery 镜像为准，不回到旧 config/query-only 镜像。

保留 r13x frontend/migration、最终派生 backend/Celery、synthetic snapshot、seed-c9-effect.py 和必要测试依赖；准确身份从结果读取，不复制多套 hash 表。r13x 冻结快照不改。Stage 4 的真实本地效果只有 agent_session/graph/search 本地投影；外部 sinks 为声明的未实现/未调用范围，不升级为外部 provider 成功。

## 2. 整阶段目标

按冻结 04 第 8 节实现本地“发现故障、停止、恢复、验证”闭环，复用已有监控、告警、备份/迁移/回滚工具。不是再做一轮 Stage 4，不建设通用运维平台，不把远端发布补齐作为前提。

1. 启动任务专属 Compose 和真实 collector，证明实际 scrape；核对 request、worker、provider、DB、queue、projection、authority 和版本指标及日志/trace 的 request/run/project/制品归属。未调用 provider 的指标不能伪称真实外部请求。
2. 用现有告警规则和有界本地刺激验证关键错误率、延迟、队列、DB连接、provider failure、authority mismatch、projection drift 的触发及恢复。可用已有模拟故障验证规则，但标明模拟与实际运行观测；不得产生付费调用或公网故障来补告警。以已有规则阈值为准，无依据不追加长期 soak、压力测试或全新故障矩阵。
3. 对带有 Stage 4 类真实本地效果/receipt 的任务数据库备份，恢复到独立任务实例，核对数据、scope、generation、journal/receipt/idempotency不变量。与 Stage 4 空/种子快照区分，不以备份命令 exit 0 代替恢复验证。
4. 用既有迁移路径演练 forward、一次有界失败及适用 downgrade 或 forward-fix，保留任务数据。已有有效 Stage 4 迁移证据按依赖复用；这里只补恢复语义，不无差别遍历历代迁移。
5. 演练 backend/frontend 镜像回退、配置/任务凭据 revision 回退，记录目标与回退后能力上限。不能把缺少新 C9 功能的旧镜像冒称功能等价。凭据仅用任务自有值，不修改用户原 env。
6. 验证 successor/legacy 路由回退保持 journal/receipt、无重复 effect。未开放 legacy writer 不为演练而开放；使用既有停用/路由恢复路径，证明停止新effect及恢复后的exact replay。无实际适用路径须说明事实和最小恢复替代，不虚构旧系统接管。
7. 记录实测 RPO/RTO、已观察的数据损失范围及必要人工步骤；不凭一次成功承诺任意生产容量或恢复时限。

## 3. 自主执行与资源

本地测试数据写入、必要实现修复、相关接口接线和任务资源创建沿用户已批准范围自主完成；小修就地处理，只复测实际受影响行为。共享源码保留他人改动，多个独立工作面可按 AGENTS 分派，但不能并行争用同一数据库、端口或 builder。以完成整个 Stage 5 为目标，不因进度回传暂停等重新发放。

使用唯一 Stage 5 project/端口/卷，不能使用 Stage 4 名称导致清理冲突。Stage 4 旧产物清理由原任务负责；在确认保留输入清单后可并行开展无冲突工作，不删对方资源。禁止全局 prune，保护 Docker 旧备份、ops-scrapyd、宿主Redis及未知数据。只保留当前和真实回退/恢复所需版本。

不 push、不 registry publish、不签名、不远端部署、不接生产数据，不启动 Stage 7–9。Stage 6 由监督在本阶段验收后派发。禁止用额外 authority/schema/validator 平台代替现有实现。

## 4. 验收与回传

上述要求都有准确范围的实际结果、恢复后数据不变量和无重复effect证据、可运行恢复说明、明确未覆盖外部范围及资源交接，才能回传本地 PASS。模拟、未执行和不适用项分别记录，不删阈值或隐藏失败。

使用 `stage5-evidence/` 一个主结果、必要脱敏日志/测试结果、索引和 RUNBOOK；记录最终输入、命令/退出码、证据复用、实际指标与恢复时间、修改文件、风险及 Stage 6 输入。不要保存完整密钥或敏感正文。稳定后一次性更新最终身份和索引。

必须向上述监督发送 `STAGE_RESULT(stageId:S5)` 和结果/索引/运行说明路径，完成整个阶段后统一审核。同阶段返工留在原任务。只有真正超范围权限/语义决策且已无独立工作时才停止；不要以普通缺口宣告整阶段不可推进。审核通过后执行19中的旧产物清理并回传实际空间变化，保留Stage6独立复核/恢复必要输入。
