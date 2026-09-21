# 全阶段收敛执行补充规则

- Date: `2026-09-07`
- Status: `ACTIVE_EXECUTION_AMENDMENT_NOT_AUTHORITY`
- Authorization: 用户明确要求按完整批次方案重新调度，并用于后续 Stage。
- Scope: 当前 Stage 1/2 返工、Stage 3 及后续已获准阶段的执行顺序；不减少实现面、门禁或证据，不授予后续阶段权限。

本规则补充既有冻结计划与合同，不改写历史字节。与旧的普通修复逐项报审、过早冻结、先跳阶段再发现可预见问题的调度方式冲突时，以本规则为准；既有安全、authority、阶段准入和不可变历史边界不变。

## 1. 唯一执行批次与任务归属

原 Stage 1/2 任务 `01a074e1-da0d-7a70-9c45-daff7b8bc9ad` 是当前修复、集成、绑定、候选预演和最终 successor 的唯一 owner。保留已完成修改和正在执行的有效工作包，不重新开始。

原 Stage 3 任务 `01a074c0-5786-7121-8a0b-ffef1e32a2a9` 并行负责环境/外部准入的只读准备与完整门禁覆盖核对，不再重复跑 v6，也不与 Stage 1/2 并写源码或绑定。后继候选阶段验收后，继续在本任务执行 Stage 3 最终验证。

执行任务自主诊断、修复、补测、重跑；只回传完整批次/阶段结果或真正需要用户决定的事项。每个 Stage 复用原任务，只有新 Stage 使用不同任务。Supervisor 不逐项审核可自主完成的修复。

## 2. 当前四个并行工作包

Stage 1/2 owner 复用现有子 Agent，按当前文件重叠调整边界，不为形式额外启动重复 worker。每包固定目标、输入、输出、允许读写范围和验收命令。

| 工作包 | 完整输出 | 共享写限制 |
| --- | --- | --- |
| 后端与架构 | 后端真实失败、三个架构 gate、registry/候选遗漏与必要回归 | 不自行改 aggregate、候选清单或冻结记录 |
| 前端 | 依赖、lint、typecheck、build、Storybook、完整 e2e | 锁文件与 workspace 安装由指定单一 owner 写 |
| 构建与供应链 | FROM digests、三个角色制品入口、重建、SBOM/provenance/扫描所需实现 | 不写 remote/registry/signing；不把预演制品当正式发布制品 |
| 安全与环境 | B324、泄漏发现裁决、非 PyPI 审计覆盖、专用测试环境与隔离 | 不输出秘密；不连既有用户/生产 DB；环境资源单 owner |

registries/sketches/baseline、共享锁文件、intake/manifest、Stage1 aggregates 和 mutable progress 必须明确单 writer。已完成工作按当前字节确认后复用，不为重排重复实现。Stage 3 的只读环境盘点向上述 owner 提供输入，不抢占其资源。

## 3. 先固定环境，消除失真的反馈

在长测试前固定 Python/依赖、前端 lockfile、cwd/PYTHONPATH、专用 DB、容器资源和网络策略，并写明与真实 workflow 的差异。需要真实服务的测试先确认专用服务可用，不连接默认 localhost 用户实例来试探。

不得临时更换 guard 异常类型让断言变绿；DNS 失败注入不是全面网络隔离。安全隔离必须覆盖该测试实际使用的 Python/native/subprocess effect；做不到时只阻断相关测试，记录精确原因。以同一环境识别源码失败、投影遗漏、测试隔离差异、服务缺失、外部权限五类问题。

## 4. 冻结前进行候选形态的完整预演

用正式 materializer 相同的 base overlay、UPSERT/DELETE、依赖安装、工作目录和候选内路径产生唯一临时预演副本。不能只在 dirty 源目录测试，也不能只核验“manifest 已选文件”而忽略预期完整实现面的漏选。

从冻结阶段计划、workflow、build/test入口及已知失败集合建立完整 gate inventory：至少包含 backend unit/integration/core/successor、architecture/registry/law/negative、frontend 全链、migration/PostgreSQL、security、Docker/full-stack、制品与供应链。每项记录 owner、依赖、命令、输入身份、实际结果和 blocked_by。不得把某一 selector 的 deselected 当其他门禁已覆盖。

局部修复运行受影响 focused tests；集成预演覆盖全部本地可执行门禁。发现问题在同批次内修复，不每项制造正式 successor。具备条件的完整测试不得延后至 Stage 3 才首次发现源码/依赖缺口。

环境或权限阻塞不能冒充通过，但不阻止无依赖工作。若完整预演仍因真实外部条件无法执行，回传批次结果及集中 blocker，不发布“全闭合”声明，不靠反复冻结候选绕过阻塞。

## 5. 统一绑定与最终候选

源码批次稳定后，由集成 owner 一次按依赖顺序执行：最终源码字节 → 受影响 family fragments → family manifests/candidates → Stage1/all-lines aggregates → Stage2 manifest/closure。测试需要临时绑定时可在预演副本生成非权威记录；不得覆盖历史或提前宣布正式绑定完成。

源码再次变化必须使相应见证失效，重跑受影响检查并重算依赖闭包，不能保留旧 PASS。最后生成 create-only successor；输入或目标已存在时不覆盖，不把每个局部修复都升级成新正式版本。

最终验收必须在最终候选字节上运行规定完整门禁并绑定 commit/tree、环境、日志/JUnit与hash。预演结果、缓存、源工作区 PASS 仅用于诊断和准备，不能替代最终候选验证。重复性验证仍按冻结要求执行。

## 6. 后续每个 Stage 的强制入口检查

每个阶段开始前，owner 先列完整退出条件及依赖，提前检查下一阶段已知的输入、环境、制品和权限前置条件。只允许不越过授权边界的准备；不提前执行未来阶段 live 操作或编写未经准入的执行合同。

远端 exact SHA、required enforcement、registry、签名、staging/production authority 与观察窗口作为独立外部工作流提前准备。无权限时集中列出精确动作、目标、scope、风险与 owner，交用户决定；不得用反复本地测试替代这些事实。

每次阶段回传必须展示全部门禁覆盖，而不是仅展示通过数。任何未执行、skip、环境差异、scanner 覆盖缺口和残余失败必须保留身份及真实依赖。后续合同必须引用本规则；Stage 4 当前仍未准入。

既有 NO_DEPLOY/NO_LIVE/NO_PRODUCTION_WRITE/NO_EXTERNAL_DELIVERY/NO_CANARY/NO_CUTOVER/NO_AUTHORITY_TRANSFER/NO_LEGACY_RETIREMENT/NO_PUSH/NO_REMOTE_MUTATION/NO_REGISTRY_WRITE/NO_SIGNING_WRITE 上限不变，除非用户以后明确授予相应具体权限。
