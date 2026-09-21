# MRW 生产部署阶段计划（v1）

- Status: `EXECUTION_PLAN_V1 · STAGE_0_IN_PROGRESS_90_TO_95_PERCENT · STAGE_1_BLOCKED_BY_STAGE_0 · PRODUCTION_RELEASE_NOT_AUTHORIZED`
- Date: `2026-09-05`
- Deployment strategy: `REMEDIATION_INCLUSIVE_RELEASE`
- Normative release plan: `00_formal-production-release-development-plan.v1.md`
- Frozen gap ledger: `01_formal-production-release-gap-ledger.v1.json`
- Mutable release progress: `03_formal-production-release-progress.v1.md`
- Functorial completion evidence: `docs/governance/functorial-debt-zero-baseline-progress.v1.md`
- Prior operational runbook: `../2026-08-30-functorial-successor-migration/production-readiness/production-runbook.md` (`DOCUMENTED_NOT_EXECUTED`)
- Prior security checklist: `../2026-08-30-functorial-successor-migration/production-readiness/security-checklist.md` (`CHECKLIST_DOCUMENTED`)
- Prior monitoring and rollback plan: `../2026-08-30-functorial-successor-migration/production-readiness/monitoring-and-rollback.md` (`RECOMMENDATION_NOT_IMPLEMENTED`)

本文档把函子式重构完成设为生产部署的 `Stage 0`。Stage 0 是后续部署工作的必要前提，但不是正式发布候选、生产运行证据或生产授权。本文只定义有序执行路径、阶段门禁、证据和回退要求，不授权 live provider、生产 canonical write、外部交付、部署、canary、cutover、authority transfer、凭据创建或 legacy retirement。

若本文与冻结的正式发布计划、缺口台账或已签发的 authority record 冲突，以冻结文件和更严格的权限边界为准。本文是执行视图，不替代事实源。

## 1. 部署对象与不变量

生产部署对象不是当前工作目录、某次测试结果或一个 Git tag，而是同时绑定以下事实的 qualified release：

```text
领域与结构闭合
  -> 干净 exact candidate
  -> 由该 candidate 构建的不可变制品
  -> 同一制品在 staging 的运行、迁移和恢复证据
  -> 独立 exact-candidate review
  -> 有边界的人类 promotion authority record
  -> 可停止、可读回、可回退的生产部署
```

该顺序默认不可交换。尤其禁止：

- 用 Stage 0 的 architecture/law 通过替代候选身份、运行安全或发布授权；
- 在候选 commit/tree 固定前生成最终测试、制品或运行证据；
- 用本地 build、bind mount 或 floating image 充当不可变发布制品；
- 用 health check、dry-run、preflight、模拟或历史候选证明生产完成；
- 在没有 rollback owner、stop path 和 promotion record 时进入 canary 或 cutover；
- 由 dashboard、manifest、checker 或 Agent 生成生产 authority。

跨阶段必须保持：

- 一个 canonical candidate identity：`commit + tree`；
- backend、frontend、migration、configuration 和 evidence 均绑定同一 release identity；
- derived preflight 始终保持 `authoritative=false`；
- legacy 与 successor 的 claim/write authority 不双写；
- 失败、跳过、阻断和未执行状态不得被汇总为 PASS；
- runtime 成功不改变 semantic、qualification 或 authority 状态。

## 2. 当前阶段快照

| Stage | 名称 | 当前状态 | 当前证据或阻断 |
| --- | --- | --- | --- |
| 0 | 函子式重构完成 | `IN_PROGRESS_90_TO_95_PERCENT` | 结构债务归零子门已完成；deferred/declared-loss 语义面、current-byte 全量一致性和 kit 剩余门禁尚未最终收口 |
| 1 | 生产合同实现闭合 | `BLOCKED_BY_STAGE_0` | Stage 0 完成后再进入；已知后续项包括两个 Alembic heads、R3 八个失败族和 R4-R8 实现缺口 |
| 2 | Exact candidate 冻结 | `BLOCKED_BY_STAGE_1_AND_DIRTY_TREE` | 文档编写前 checkout 有 936 tracked 状态项、至少 1550 个具体 untracked 文件；落后 `origin/main` 21 commits |
| 3 | 候选验证与不可变制品 | `NOT_STARTED` | 无绑定当前 candidate 的 required CI、backend/frontend digest、SBOM、provenance/signature |
| 4 | 隔离 staging runtime | `NOT_AUTHORIZED` | 当前只观测到 PostgreSQL、Redis 运行；完整应用栈未形成 staging receipt |
| 5 | 运行资格与恢复闭合 | `NOT_STARTED_OR_DOCUMENTED_ONLY` | 无真实 telemetry、restore、migration/image rollback 和 RPO/RTO receipt |
| 6 | 独立候选资格审查 | `NOT_STARTED` | R9 前置的 G0-G8 candidate-bound evidence 未齐 |
| 7 | 有界生产晋升授权 | `NOT_AUTHORIZED` | 无绑定当前 candidate、artifact、scope、rollback owner 的人类 authority record |
| 8 | 有界 canary | `NOT_AUTHORIZED` | 无完整 telemetry、stop condition、独立 ingress/route flag 与 canary authority |
| 9 | 生产放量与稳定收口 | `NOT_STARTED` | 依赖 Stage 8 canary receipt 和仍有效的 promotion scope |

Stage 0 当前并未整体完成。已经完成的是冻结的结构债务归零子门；历史 local-only exact candidate `452611fccb69188477f277550a7f8b6c98b4724c` 已通过当时字节的独立审查，但不能证明后续 remediation bytes 已完成重构收敛。B12 只绑定 C7 evidence family，也不是 Stage 0 总体验收或完整 release candidate。

## 3. Stage 0：函子式重构完成

### 目标

确认领域对象、态射、有序组合、canonical representation、projection authority、effect boundary 和 closed failure family 已按冻结范围落地，并由机械 gate 见证。

### Stage 0A：已完成的结构债务子门

- S0-S8 冻结结构治理包全部完成；
- `derived-marked`：514 accepted，0 remaining；
- `no-throw-in-core`：213 accepted，0 remaining；
- architecture exact keys：727 accepted，0 remaining；
- `arch-baseline.json` 是空数组，SHA-256 为 `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`；
- resolution ledger 共 727 条，SHA-256 为 `771351d21174e21685961e536ae9a617effa574bceee24d5f4626cb9c68d0a58`；
- fresh architecture gate：`285 passed`；
- B12 C7 exact-byte family candidate：`CANDIDATE_VALID_NOT_AUTHORITY`。

这些结果证明 architecture scanner 所登记的两类债务已经物理修复并完成机械登记，但不能推出所有函子语义面、全部实现解释器和所有 kit 运行时都已收口。

### Stage 0B：仍需完成的重构工作

1. 对 `CrawlerProvider` 作最终语义判定：若确实形成两个或以上可替换解释器，则补共享 typed Scrapyd effect boundary、closed failure family 和同一 law suite；若仍只有一个实现且无替换压力，则登记为明确的 `NOT_APPLICABLE`，不得制造假 port。
2. 复核 market/policy iteration、collect execution/routing、provider-specific operational conversion 等 declared-loss 边：每项必须有保留内容、损失内容、调用方影响、替代路径和 witness；无法接受的 loss 必须实现修复，不能只靠分类关闭。
3. 将 Stage 0A 后发生的源码变化重新绑定到当前 registry、sketch、authority map、failure map 和 family-level exact-byte evidence，消除旧 candidate/current bytes 混用。
4. 对当前字节运行完整的非生产函子验收：successor runtime、architecture、law、failure/negative、codec、projection、recovery、backend/frontend integration；所有 skip、deselect、environment block 和 native abort 必须逐项归属。
5. 完成适用的 kit 多语言与静态门禁，或给出精确的不适用裁决。当前已知未闭合记录包括 TypeScript dependencies、Rust default-feature compile、Pyright、Clippy 和 fmt；不能把 Python architecture `285 passed` 等同于 kit 全量通过。
6. 对当前全仓残余失败重新取证。历史隔离运行的 `76 failed / 2453 passed / 921 skipped / 1 deselected` 虽未命中 successor-runtime、architecture、functorial、exact-byte 或 failure-registration，但仍需证明这些失败与 Stage 0 声明范围无依赖，或完成修复。
7. 生成一个独立的 Stage 0 completion record，绑定上述决策、命令、测试计数和证据摘要；该记录保持 `NOT_AUTHORITY`，且不承担 Stage 2 的 Git candidate 职责。

### Stage 0 完整退出条件

- architecture baseline 保持 0，fresh scan 的 new/stale 均为 0；
- 当前声明范围内不存在未解决的 canonical representation、ordered composition、effect boundary、failure family、authority direction 或 law witness 缺口；
- deferred 与 declared-loss 项逐条变为 accepted implementation、accepted explicit loss 或 justified `NOT_APPLICABLE`，不存在笼统 deferred；
- registry、sketch、maps、family evidence 与当前源码字节一致；
- 适用 kit gate 全绿，不适用项有机器可读或冻结文字裁决；
- 当前字节的非生产全量回归通过，或所有负项均有精确 owner、原因、与 Stage 0 无依赖的证明；
- 独立复核接受 Stage 0 completion record，状态为 `FUNCTORIAL_REFACTOR_COMPLETE_NOT_PRODUCTION_QUALIFIED`。

### Stage 0 输出

Stage 0 输出的是可进入发布收敛的实现和结构证据，不输出以下对象：

- 正式 remediation-inclusive release candidate；
- production artifact；
- live-provider、canonical-write 或 cutover authority；
- staging、canary、backup/restore 或生产运行 receipt；
- production promotion record。

### 回归规则

Stage 0A 在当前验收边界已完成；Stage 0 整体仍在进行。后续改动若造成 architecture new key、failure family 漂移、authority reverse write、codec/identity 漂移或 law witness 失效，应把受影响项重新打开。不得直接重写 baseline 隐藏回归。

## 4. Stage 1：生产合同实现闭合

### 目标

在候选冻结前完成所有预期会改变源码、workflow、依赖、Docker、迁移、生产配置和运维工具的工作。Stage 1 只证明生产合同实现闭合，不创建部署权力。

### 工作包

1. 处理当前两个 Alembic head，选择并实现显式 merge revision，或修改并验证明确的多 head 策略；禁止继续让 entrypoint 的 `alembic upgrade head` 对多 head 失败。
2. 修复 R3 的八个静态生产失败族：floating image、默认凭据、ES security、公共端口、版本占位/漂移、required-check 覆盖和不可变制品元数据。
3. 完成 R4 workflow：把 formal release、backend、frontend、migration、security、Docker 和 evidence checks 纳入可强制的 CI；不得用只聚合部分 job 的绿色 gate 掩盖失败。
4. 完成 R6 runtime 实现：production project resolver、认证、scope/actor/approval、rate/body/CORS/TLS、provider 和 canonical-write policy。
5. 完成 R7 控制实现：domain/route/version metrics、alert rules、canary route flag 或独立 ingress、stop conditions。
6. 完成 R8 运维工具：backup/restore、migration forward/failure/recovery、image/config rollback 和 receipt 生成；真实演练留到 Stage 5。
7. 关闭根/backend/frontend 版本和 release identity 漂移，固定依赖与生产 build contract。
8. 为以上所有实现运行 focused tests；只有 Stage 1 完整批次结束才运行集成检查。

### 必需证据

- Alembic 单 head 或显式多 head 策略的 focused evidence；
- R3 静态检查对实现面 PASS；
- CI DAG 完整性和 fail-closed 聚合测试；
- production resolver、认证、provider、authority 和 canonical-write negative tests；
- metrics/alerts/canary/stop-path 配置校验；
- backup/restore/migration/image rollback 工具的 dry-run、参数防护和 fixture tests；
- Stage 0 architecture gate 无新增回归。

### 失败条件

- migration graph 非确定，或 `alembic upgrade head` 仍产生 multiple heads；
- R3 仍有红项；CI aggregate 允许必需 job 失败；
- production endpoint、metrics、provider 或 canonical writer 缺少明确认证与 authority owner；
- rollback 工具只能恢复 compose/env 文本而不能覆盖声明的恢复对象；
- 为满足静态 gate 而隐藏 failure、放宽安全默认值或抹除真实运行差异。

## 5. Stage 2：Exact candidate 冻结

### 目标

把 Stage 0-1 的全部必要修改收敛为一个干净、可审查、可重放的 remediation-inclusive commit/tree。Stage 2 后任何源码、workflow、Docker、lockfile、migration 或生产配置变更都会使 Stage 3-8 证据失效，并必须退回 Stage 1/2。

### 工作包

1. 列出当前修改，按用户工作、重构实现、生产合同、生成证据、历史产物和本地运行数据分类；不得 reset、clean 或丢弃不明来源修改。
2. 排除密钥、缓存、数据库、临时日志和不应成为候选的历史运行产物。
3. 与最新 `origin/main` 做受控整合，解决当前 21-commit drift。
4. 在隔离 checkout 中形成唯一 commit/tree，记录分支、版本和 candidate strategy。
5. 重新绑定 Stage 0、Stage 1 和 release evidence 输入。
6. 运行 R1；tracked 与 untracked 必须均为 0。

### 退出条件

- `git status --porcelain=v1 --untracked-files=all` 空输出；
- `git rev-parse HEAD HEAD^{tree}` 与 candidate record 一致；
- R1 `candidate-identity` PASS；
- 候选包含 Stage 1 全部必要实现，不依赖未跟踪文件或 bind-mounted source；
- 冻结 evidence、registry、manifest 和实际源码 hash 相符。

历史 exact candidate 和 B12 family candidate 只作来源证据，不能替代本阶段的新 candidate。

## 6. Stage 3：候选验证与不可变发布制品

### 目标

使 Stage 2 exact candidate 的完整验证成为远端不可绕过的 required checks，并只从该 candidate 构建可复现、可验证、可回退的 backend/frontend/migration 制品。

### 要求

- R1、R2、R3 全部针对 Stage 2 candidate；
- backend unit、integration、core-business、schema/migration、successor runtime 全量门禁；
- architecture、registry、law、exact-byte 与 negative/failure tests；
- PostgreSQL opt-in tests 使用专用数据库，teardown residue 为 0；
- frontend install、lint、typecheck、build、component/e2e；
- Bandit、`pip-audit`、gitleaks、frontend dependency audit；
- Docker build 与 full-stack smoke；
- GitHub branch protection 或 ruleset 的 live API readback 证明必需 job 不可绕过；
- 固定所有 base image 和 compose image digest，移除生产路径的 floating `latest`；
- 生产 compose 不 bind mount checkout 源码；
- 使用 lockfile 和 clean build context；
- backend、frontend、migration runner 分别产生 immutable digest；
- 生成 SBOM、build provenance、漏洞扫描结果和签名/验证结果；
- release manifest 绑定 candidate commit/tree、制品 digest、构建 run 和工具版本；
- artifact registry 使用不可变 tag 或 digest promotion，不允许覆盖同名制品。

### 退出条件

workflow 对 candidate SHA 运行且必需 job 全部 PASS；完整 run id、head SHA、job conclusions、skip/deselect/warning 清单进入 evidence。在第二个干净环境按相同 candidate 重建，输出 digest 一致；若平台差异导致不可做到 bit-for-bit，必须声明差异域并以签名 provenance 和运行等价门禁替代，不得宣称完全可复现。

任何失败若需要改源码、workflow、Docker、migration、lockfile 或配置，必须退回 Stage 1，重新产生 Stage 2 candidate，不能就地修补 Stage 3 制品。

## 7. Stage 4：隔离 staging runtime

### 目标

使用 Stage 3 的同一不可变制品，在无生产流量的隔离环境验证生产配置、身份、权限、网络、provider、canonical-write policy 和完整 runtime realization。该阶段需要单独 staging authority；Stage 0 不授予这些权限。

### 准入与运行安全要求

- secret manager 或权限受限的只读 secret file；不得使用 `0644` 明文生产 `.env`；
- TLS、secure cookie、明确 CORS allowlist、body size 和 rate limit；
- successor、admin、metrics、health-deep 的认证/网络边界明确；
- production project resolver、actor binding、scope、approval 和 authority epoch 可读回；
- provider allowlist、timeout、retry、quota/cost ceiling、credential revoke 和日志脱敏；
- canonical-write owner 唯一，legacy/successor 不双 claim、不双写。

### 执行顺序

1. 恢复生产近似但脱敏的数据快照；
2. 验证 backup digest 和恢复环境身份；
3. 运行 migration preflight 和 schema diff；
4. 启动 PostgreSQL、Elasticsearch、Redis、backend、Celery 和 frontend；
5. 验证 `/health`、`/health/deep`、worker ping、frontend/API proxy；
6. 执行只读业务 journey 和 successor query；
7. 在单独授权后执行最小写入、readback、idempotency 和 failure/recovery journey；
8. 记录服务、配置、schema、制品和数据快照 identity。

### 退出条件

- 所有服务使用 immutable digest 且健康；
- migration fresh/upgrade 路径均通过；
- worker、API、frontend、database、search 和 provider receipt 可关联到同一 trace/release；
- staging 没有 production ingress、生产密钥或隐式 canonical authority；
- 所有测试写入可清理，teardown residue 为 0 或有明确 retained evidence owner。

## 8. Stage 5：运行资格与恢复闭合

### 目标

证明系统不仅能启动，还能在失败后被发现、停止、恢复和验证。

### 可观测性门禁

- metrics 被真实 collector scrape，而不只是存在 `/metrics`；
- 请求、worker、provider、database、queue、projection、authority 和 release-version 指标齐全；
- 日志与 trace 关联 request/run/project/candidate，不泄漏凭据和正文；
- 告警规则覆盖错误率、延迟、队列积压、DB 连接、provider failure、authority mismatch 和 projection drift；
- 每条关键告警都有触发与恢复测试。

### 恢复门禁

- PostgreSQL backup/restore 到独立实例并校验数据不变量；
- migration forward、failure、rollback/downgrade 或 forward-fix 路径演练；
- backend/frontend image 回退；
- 配置和凭据 revision 回退；
- successor/legacy route 回退保持 journal 和 receipt，不重复 effect；
- 实测 RPO、RTO、数据损失范围和人工操作步骤。

当前 `rollback.sh` 只保存 compose、env 和 Git HEAD 文本，不能作为数据库、schema、代码或镜像完整恢复证据。

## 9. Stage 6：独立候选资格审查

### 准入

Stage 0-5 全部 PASS，G0-G8 均有绑定同一 candidate/artifact/environment 的 exact evidence，且没有被隐藏的 `BLOCKED` 或 `UNEXECUTED`。

### 审查要求

- 独立 reviewer 重算 candidate、artifact、configuration 和 evidence digest；
- 验证 CI enforcement、security、runtime、provider、observability 和 recovery receipt；
- 验证声明的 loss、skip、unsupported capacity 和环境边界没有被提升；
- 验证 manifest 为 `authoritative=false` 的派生对象，不能创建 promotion authority；
- 任一 source/config 字节变化均使审查失效并退回 Stage 1/2。

### 退出状态

只允许输出 `FORMAL_RC_READY_NOT_PRODUCTION_AUTHORITY` 或负状态。独立审查不能自行部署、签发凭据或开启生产写入。

## 10. Stage 7：有界生产晋升授权

### 准入

Stage 6 输出有效的 formal RC，且 rollback owner、stop path、部署窗口和上一已知良好版本均已确定。

### Promotion record

必须由人类或组织 authority 单独签发，并至少绑定：release identity、artifact/config digest、允许的 capability/project/traffic scope、部署窗口、操作人、审批人、rollback owner、stop conditions、上一已知良好版本、有效期和撤销方式。

### 退出状态

`PRODUCTION_QUALIFIED_FOR_DECLARED_SCOPE`。该状态只授权记录中明确的 canary 范围，尚不表示已经部署或允许全量流量。

## 11. Stage 8：有界 canary

### 准入

Stage 0-7 全部 PASS；promotion record 仍在有效期内，监控、告警和回滚均在线。

### 顺序

1. shadow/read-only observation；
2. 单一内部项目或 allowlist project；
3. 最小可逆写入能力；
4. 逐 capability 扩展，不进行全局流量切换；
5. 达到观察窗口后才扩大范围。

### Stop conditions

至少包括：error/timeout 超阈值、authority/readback mismatch、duplicate effect、projection drift、queue starvation、数据不变量失败、provider quota/cost 超限、告警或 rollback path 不可用。

任一 stop condition 触发即停止新的 dispatch/claim，保留事实日志和 receipt，执行预先绑定的 route/image/config rollback；不得删除 successor events 或把已完成 effect 重新解释为未执行。

## 12. Stage 9：生产放量与稳定收口

### 必需输入

- G0-G8 全部 PASS 的 exact release-evidence manifest；
- 当前 candidate commit/tree；
- immutable artifact digests 和签名验证；
- required CI live readback；
- staging、security、provider、observability、canary 和 recovery receipts；
- Stage 6 fresh independent exact-candidate review；
- Stage 7 promotion authority record；
- Stage 8 canary receipt，且原授权覆盖本次放量范围。

### 部署顺序

1. 再次验证候选、制品签名和环境 identity；
2. 创建部署前数据库/配置 checkpoint；
3. 应用 migration，并在服务开放前做 schema/data readback；
4. 按 Stage 7 授权且经 Stage 8 验证的 route scope 部署；
5. 执行 health、business journey、write/readback 和 telemetry 验证；
6. 在观察窗口内保持可立即 rollback；
7. 只在所有 receipt 完整且 stop condition 未触发时扩大流量。

部署命令不得在本文预先固化真实凭据、生产主机或 destructive database 参数；这些必须来自已批准的环境 runbook 和 authority record。

### 退出条件

- 完成预先声明的稳定观察窗口；
- SLO、error budget、provider quota/cost、queue backlog 和数据一致性处于阈值内；
- 无未解释的 authority、readback、duplicate effect 或 projection drift；
- backup/restore 计划和 on-call owner 进入持续运行；
- post-deploy review 与 incident/deviation 清单完成；
- legacy retirement 如需进行，另立任务、另做证据和授权，不随生产部署自动发生。

## 13. 依赖关系与并行边界

主依赖链：

```text
Stage 0
  -> Stage 1
  -> Stage 2
  -> Stage 3
  -> Stage 4
  -> Stage 5
  -> Stage 6
  -> Stage 7
  -> Stage 8
  -> Stage 9
```

Stage 1 内的 migration、CI、security/runtime、observability/canary 和 recovery-tool 工作可在写路径不冲突时并行；共享 authority schema、composition root 和 workflow 聚合保持串行。Stage 3 的 backend、frontend、PostgreSQL/security tests 和镜像构建可并行，manifest 聚合最后串行。Stage 5 的监控 soak、容量验证与恢复 drill 只有在隔离资源和 effect 不冲突时才能并行。Stage 2、4、6、7、8、9 是身份冻结、运行 realization、资格、授权、canary 和放量边界，必须按结果依赖串行。

每个并行任务必须声明：目标、输入 candidate/artifact、允许写入范围、输出 evidence、focused acceptance、failure owner。单个分片只运行 focused tests；完整批次或阶段边界才运行全量 suite、证据登记和 candidate rebind。

## 14. Evidence 登记

每个 Stage 的完成记录必须包含：

```text
stage_id
status = PASS | FAIL | BLOCKED | UNEXECUTED
candidate_commit
candidate_tree
artifact_digests[]
environment_identity
commands[]
test_counts
evidence_refs[]
evidence_sha256[]
observed_at
owner
reviewer
authority_ref
rollback_target
open_failures[]
```

Stage 0 可引用既有治理与 B12 evidence。Stage 1 起不得只引用 mutable progress 文本，必须绑定原始命令输出、机器可读 artifact 或不可变 review record。所有 manifest、dashboard 和 readiness summary 都是 derived projection，不是 authority source。

## 15. 当前下一步

当前应继续完成 Stage 0，Stage 1 尚未准入。优先顺序：

1. 冻结 Stage 0B 的 residual scope、owner、写路径和验收证据；
2. 并行处理 deferred/declared-loss 语义审查、current-byte evidence rebind 和适用 kit 门禁；
3. 统一运行当前字节的函子/后继/集成验证并登记负项；
4. 生成并独立审查 Stage 0 completion record；
5. Stage 0 通过后，进入 Stage 1 修复 Alembic 双 head 并关闭 R3、R4、R6、R7、R8 的实现缺口；
6. Stage 1 完成后才进入 Stage 2 建立干净 exact candidate；
7. 只有 candidate identity 固定后，才进入 Stage 3 全量 CI 与不可变制品。

在 Stage 1 完成前，项目的准确状态是：

```text
FUNCTORIAL_REFACTOR_STAGE_0_IN_PROGRESS_90_TO_95_PERCENT
STRUCTURAL_DEBT_ZERO_SUBGATE_COMPLETE
CURRENT_RELEASE_CANDIDATE_NOT_ESTABLISHED
PRODUCTION_RELEASE_NOT_AUTHORIZED
```
