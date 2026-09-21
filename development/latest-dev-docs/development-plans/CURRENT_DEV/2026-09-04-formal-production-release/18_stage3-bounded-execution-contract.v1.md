# Stage 3：候选验证与制品执行合同

## 当前阅读入口

Stage 3 已按第 2.2 节完成本地交付，结果见 [r13x 本地交付结果](stage3-evidence/r13x/local-delivery/local-stage3-delivery-result.r13x.json)；正式发布资格仍后置。当前阶段及准入只读取 [06 顶部执行入口](06_production-deployment-stage-progress.v1.md)，Stage 4 执行 [20 号合同](20_stage4-local-runtime-contract.v1.md)，流程规则统一读取 [19](19_direct-testing-batch-freeze-amendment.v1.md)。不因本文件保留历史未闭合记录而重启已验收的 Stage 3 本地工作。

## 历史输入与派发记录

以下覆盖段、日期、状态及候选身份保留当时含义，不作为当前派发入口；正文旧 r13l 路径同样仅代表初始输入。需要核对 Stage 3 范围时读取第 2.1/2.2 节；普通 Stage 4 执行不逐条继承这些历史重试要求。

> 2026-09-13 最新用户范围：当前只完成本地交付；推送、发布、远端保护和签名等后置，不再阻塞本地收尾。以第 2.2 节为当前执行口径，优先于下方正式发布准入及历史等待要求。用户允许安全注入密钥并做本地有界 provider 验证，不等于已取得密钥或授予远端发布权限。

> 2026-09-13 用户批准阶段过渡裁定：以第 2.1 节区分 Stage 3 验收和最终完整 R2，不再用后续阶段证据阻塞先行阶段。当前输入为 r13x，准确身份、证据与权限缺口统一引用 [r13x 最终结果](stage3-evidence/r13x/stage3-final-reconciliation.r13x.json)；下方 r13v 及更早状态仅为历史。本次只解除阶段顺序矛盾，不建立 Stage 3 PASS、Stage 4 准入或外部写入权限。

> 2026-09-13 强制必读：[19 号流程缩减规则](19_direct-testing-batch-freeze-amendment.v1.md)。普通修复直接实施并做最小相关验证；只在真实交付边界统一冻结，制品保留至扫描及交付依赖解除。同输入同原因不反复全套重跑，进度回传后继续执行。下方历史候选及结果不改变本规则，也不代表当前任务已经完成剩余修复。

> 2026-09-12 当前输入与收敛状态（取代下方 r13s 及更早输入）：exact candidate/replay 为 `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13v`，commit `8427e3d626cd12f41e45d38e00223f2ef86d692f`，tree `4146bcab51e437920a006875e06ed8cdcc32470a`；manifest/result/index SHA256 分别为 `e182f547008d57d02f833f777aaf1ffa31236860be7d5f9106d4f81f2176e485`、`2c927ad198ad5981b0d9dc5a5013491b34590441e56a379745a11e437570c1dd`、`fef1108b38ebef03d68fcae54f023b08025de104a9d9c577022945c637838712`。Gitleaks 已按 exact finding disposition 闭合；107 项受影响测试及 exact-byte seed 的 12 项能力测试与 disposable PostgreSQL 实载证据通过。linux/amd64 backend/migration 在同一 live-input 窗口的 candidate/replay manifest/config/ordered layers 一致，但后续 recovery rebuild 因 floating apt/pip 输入产生不同 digest，且 retry4 的 Trivy OCI-tar 入口实际 `NOT_RUN`；其错误的顶层 `TRIVY_GATE_PASSED` 字段已由 `stage3-evidence/r13v/artifacts/backend-migration-amd64-final/result.json` 明确废止。当前 Stage 3 结果为 `REBUILD_REQUIRED`：下一后继必须先冻结或明确标识可变构建输入、修复 attestation statement subject、对 exact digest 建立 fresh Trivy 分母，并保留既有远端、live-provider、registry/signing 与 R2 权限边界。不得把同窗口复现、派生 preflight 或历史扫描提升为发布权限。

> 2026-09-10 最新执行规则及输入：按用户要求，小修复由发现任务直接实施、最小相关验证并合并到整个 Stage 3 回传，不再逐项转交或等待监督批准；本规则覆盖下方第 4 节及历史消息中的小修复转交/逐批审批要求。冻结 candidate/replay 不原地修改，必要身份更新使用现有路径，真实写冲突或新增权限/语义决策才协调。已收到原 owner 完成的 r13s apk.log 修复批，监督仅核对 manifest/result/index 三项 hash 与完整证据索引通过，允许作为当前 Stage 3 执行输入合并继续，不新增小修复验收门禁。Root `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13s`；commit `9224f3627fa81d03e7963450891e822f6177be38`；tree `9f9f3579df66b468373d6bb3a508d9bc3e7ef7d4`。Manifest `evidence/candidate-manifest.v5.json` SHA256 `d9a9235b0a7aa804cdfd16d6bfa0296fe1472ae9d8c3793baecf06b49e55a27e`；result `evidence/stage1-stage2-stage-result.r13s.json` SHA256 `fdeced61eeaa9cb094f1037ab838d599812a87c6af364604ee99884444937042`；index `evidence/SHA256SUMS.r13s` SHA256 `4495881c915b70ded40aad2d05b033b087ddbb3d6dbaa2c82a45f9dc23a5a9d4`。修复报告仅证明本地 linux/amd64 frontend 的 epoch0+rewrite-timestamp=true profile，不证明未显式同配置的 workflow parity 或远端资格；其他门禁和发布权限不变，最终统一审核整个阶段。后续小修复遵照此规则，不再等待监督更新本文才能推进。

> 当前有效输入（2026-09-10，取代下方历史输入）：`ACCEPTED_SCOPED_REPRODUCIBILITY_REPAIR_R13R_WITH_STAGE3_BLOCKERS`。Root `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13r`（candidate/replay/evidence）；commit `9b95d1c6c515b3013d6be7fd39ffb54801310c1c`，tree `040f2ed5b223607c63404c709e413f8898c2b504`，base 不变。Manifest `evidence/candidate-manifest.v5.json` SHA256 `ee6d13fe269c7177f0eb2b5df1aca1d50e05299b43aeeb4759093b6d1d61d439`；result `evidence/stage1-stage2-stage-result.r13r.json` SHA256 `82385e5a51940185b2fc73f3f7efa799cd4888ed13ed075cb10cf3fdfa9912de`；index `evidence/SHA256SUMS.r13r` SHA256 `4f35639c7c72126dbe00640517839d41e112f9383cc0ddd546ae6d29a955caa2`。监督核对证据索引全项通过、候选/重放身份与 clean、实际有界差异及 233 项 focused 结果。本批仅关闭 linux/arm64 backend/migration 的独立 clean build 镜像 manifest/config/layer 和 psutil 文件确定性；OCI tar 外层文件不宣称字节相同。新证据写仓库根 `stage3-evidence/r13r/`，旧证据按真实依赖和原范围复用，不重标为新 SHA fresh 运行。Gitleaks 419（批准豁免 0）、每角色 Trivy 148（135 HIGH/13 CRITICAL、无 FixedVersion）、完整服务/实际迁移及 live-provider、amd64 完整资格、准确 SHA 远端检查/保护、registry/签名与实际 release manifest 等剩余要求不因本批验收变成 PASS；不建立外部写入或发布权限。执行目标仍为完成整个 Stage 3，进度回传后自主继续，不等待逐小项发放。

> 当前有效输入（2026-09-10，取代下方所有历史输入）：`ACCEPTED_SCOPED_REPAIRS_R13Q_WITH_STAGE3_BLOCKERS`。Root `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13q`（candidate/replay/evidence）；commit `bdd765316d80efdef243927d81e2daa9de20f81c`，tree `2734ad57714d270fa79561d0bf2ee0a3a922e34c`，base不变。Manifest `evidence/candidate-manifest.v5.json` SHA256 `4da75d49384e03243d6702afff9b8acdde875ac4f448affbaa92e588ad0db68d`；result `evidence/stage1-stage2-stage-result.r13q.json` SHA256 `89dd22e1ca4ac5d065d3b2bcac040b504c508404bde8d9bc1b48347d9c77f633`；index `evidence/SHA256SUMS.r13q` SHA256 `cde93097717aa3d58b63a9643406bb09f30d3a8035cca9c3881aac8b99f824d7`。新证据写 `stage3-evidence/r13q/`。本批只接受候选输入闭包与前端修复；preview聚合1484 PASS/292 skip和前端镜像结果按明确input comparison复用，不重标为fresh最终SHA运行。最终Gitleaks419条未审定、豁免批准数0，backend/migration各148条无FixedVersion、rootfs重建差异及其他Stage3门禁仍未闭合，不建立发布权限。不应用被拒绝的gitleaks配置，不降低扫描阈值。

> 当前输入（2026-09-10，覆盖下方历史输入）：`ACCEPTED_SCOPED_HEALTHCHECK_REPAIR_R13P`。Root `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13p`（candidate/replay/evidence）；commit `342d3b3c35ad987c47990da6ac550dfe936d4818`，tree `3f87e85dce02b312e445c657c238c11c6809850e`，base 不变。有效 manifest 为 `evidence/candidate-manifest.v5.retry1.json`，SHA256 `64c04d1d3d6fc7d302d89d5247857bcd20115a83432043ea95e18bf74d52635e`；result `evidence/stage1-stage2-stage-result.r13p.json` SHA256 `c66fe0aeae3f1dec817923cea041eb25a1e03f3048e63571b42da4b4ed609cd4`；index `evidence/SHA256SUMS.r13p` SHA256 `283bd20110c12a75d49efa2ba7b922f2ae053e825d7bfeb9c70af4b35665a550`。新证据写 `stage3-evidence/r13p/`。只关闭健康检查 argv 缺陷及后继身份；匹配 argv 的 patched r13o 容器观察不是完整 r13p 部署。未变输入的旧证据按原范围复用，Stage3其余要求和权限不变；持续执行整个阶段，不等逐步骤发放。

> 最新输入（2026-09-10，取代下方 r13n/r13l 输入）：`ACCEPTED_SCOPED_E2E_LAUNCH_REPAIR_R13O`。Root `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13o`（candidate/replay/evidence）；commit `3669d4ddc19fb722058976b4e1f05e99eccfe96e`；tree `ce4e4b9ce1b633276192e809fa72007176224e0c`；base 不变。Manifest SHA256 `c0ed5c6d4c74233ac6762c56c6c5287e21e1787d2813d5093d8bddd7d643aadc`；result `evidence/stage1-stage2-stage-result.r13o.json` SHA256 `33d54413b3a8251c495c42ba972a96b8e7f10e318c295789ff67c4395fb83035`；index `evidence/SHA256SUMS.r13o` SHA256 `93a31ad1e5be5456264adbe256a2f049f3a3ea6e85fc1d7b59e577d1ada5b075`。新证据使用本目录 `stage3-evidence/r13o/`。验收仅关闭启动参数修复和后继身份；完整 E2E 的 93/5/2/12 历史结果不转 PASS。服务地址使用既有显式环境变量注入确切任务服务，不修改 fail-closed proxy 默认值。输入相同的 backend/镜像证据仅按原范围引用；不重标旧执行 SHA。以下历史输入记录、冻结候选与证据保持不变。

> 当前输入更新（2026-09-10）：Supervisor 已接受合并依赖修复后继 r13n，当前执行候选替代 r13l。以下正文中的 r13l 身份块保留为初始输入历史；后续执行使用本段 r13n。范围、权限和执行方式不变，不为更新本文重建候选。
>
> Root: `/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13n`（`candidate/`、`replay/`、`evidence/`）。Commit `33a841f43cc80f4871119f017138f0cb87a966c6`；tree `6a9d17eb373beaadccbc19d280ba492bc0df7177`；base 不变。Manifest `evidence/candidate-manifest.v5.json` SHA256 `ddb48465beddc536ea27ca2ba9799337bdc47217fbb31ffdc164e0f81fb04f2a`。Result `evidence/stage1-stage2-stage-result.r13n.json` SHA256 `7d414107b8c2728042016fc2f865d531215468b08e2fcabdf4826b853967ba8a`；index `evidence/SHA256SUMS.r13n` SHA256 `d5264c225b1d62797274e63bcd3020e0012508f4e0ed2f8caf3d93da1d6a79cf`。
>
> 新 Stage 3 证据写本目录 `stage3-evidence/r13n/`，原 r13l 证据保留。精确 r13n 的本地 backend/migration build、SBOM、扫描和 egg smoke 可引用其已验证范围；它们不证明独立重建、完整服务测试或远端资格。其他证据按真实输入/环境依赖和候选绑定要求复用，不把旧 SHA 执行重标为新 SHA。

- Date: 2026-09-09
- Status: `DISPATCHED_STAGE3 · NOT_AUTHORITY` (2026-09-10)
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Executor: `01a087e8-26ad-71d1-b701-cde619801bd9`
- Stage 1/2 repair task: `01a08002-1217-7283-89a5-499599bdc1a2`

本合同替代 `07`、`09`、`15` 的当前执行指令；这些文件保持历史原件，不再串联继承其重试、fresh 检查、字段扩展或候选输入要求。`04_production-deployment-stage-plan.v1.md` 第 6 节的实际交付要求和 Stage 3 PASS 条件保留。用户于 2026-09-10 明确要求新建开发任务，已派发上述新 Executor；旧 Stage 3 任务不再承担当前执行职责，冻结候选不变。

## 1. 已验收输入与工作目标

Stage 1/2 已由监督验收为 `ACCEPTED_SCOPED_STAGE1_STAGE2`，见 `06` 第 8 节。

```text
candidate_root=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260909-v4-r13l/candidate
replay_root=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260909-v4-r13l/replay
evidence_root=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260909-v4-r13l/evidence
commit=84e2fbc098d341cc3f2fc242f40a3be29d720421
tree=9c937baa9a92c21d201cce29af83c3ea79b1a924
base=88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6
manifest=candidate-manifest.v5.json
manifest_sha256=6c0cd7c4934d9b9bc38ee7b37ef2e2a01e1c1e6a3f64c1f88ad31394e4170d81
stage_result=stage1-stage2-stage-result.r13l.json
stage_result_sha256=741aa025c2a6841bf39c30d0432e93c27892e878d8a2057fc2e4e7fff0764f89
evidence_index=SHA256SUMS.r13l
evidence_index_sha256=87b88ebbc60493c32046e471e87516aa6e7ce0a2b79085c8af6ac5d06acef0e6
```

目标是验证这个候选并生成规定的发布制品，不继续开发发布平台。复用候选内已有 workflow、测试、构建命令、扫描器与 R2 validator；仅修复实际阻碍这些路径的缺陷。不新增通用调度器、资源租约服务、证据框架、签名平台或包发布基础设施。已有 owner、资源名称/ID 和普通记录足以表达隔离时，不另建机制。

本合同是候选外的监督执行输入。候选中的旧合同仍是历史字节；不要为同步本文、进度或措辞而改写 r13l、重建 Stage 1/2 bindings 或重新生成候选。真实产品/测试实现变化仍遵循第 4 节。

## 2. 必需交付范围

使用现有 required workflow 与 `04` 第 6 节确定命令和 selector；同一执行结果可覆盖多个要求，不把同义门禁当成多次运行。

- 候选身份及 R1/R3；按第 2.1 节验收 Stage 3 实际 manifest 中属于本阶段的要求，完整 R2 留在最终发布边界。synthetic R2 conformance 不替代实际 release manifest。
- backend unit、integration、core-business、schema/migration、successor runtime；architecture、registry、law、exact-byte、negative/failure；专用 PostgreSQL opt-in 和 task-owned 数据的 teardown residue 检查。
- frontend frozen install、lint、typecheck、build、component/e2e；Docker build 与 full-stack smoke。只使用现有规定场景，不追加压力测试、故障矩阵或跨平台兼容项目。
- Bandit、pip-audit、gitleaks、frontend dependency audit、image scan。使用既定阈值，不扩大为依赖全量审计或全面安全加固。固定 Git 依赖的公共漏洞库覆盖缺口沿用已批准的非阻塞限定，不冒充完全覆盖，也不为消除该限定而发布包；真实新漏洞和 secrets finding 仍按影响处置。
- backend、frontend、migration 三角色 immutable digest，固定 base/compose image digest、clean build context、无生产 source bind mount；SBOM、provenance、scan、签名验证及 registry immutability 证据。
- 同一候选在第二个干净构建环境重建并比较 digest；不附加第二套完整测试。不能 bit-for-bit 时沿用 `04` 的明确差异域、签名 provenance 和运行等价要求，不另造泛用等价框架。
- 对准确候选 SHA 的 required workflow/job conclusions 与不可绕过规则进行真实远端 readback；实际 release manifest 绑定以上候选、制品和证据。

远端检查、签名和 registry 要求不是可由本地绿灯替代的文书项；缺失时如实保留，不能宣称 Stage 3 PASS。

### 2.1 用户批准的非循环阶段过渡（2026-09-13）

用户已同意：Stage 3 只验收本阶段条件，后续证据在对应阶段产生，完整 R2 仍为最终发布门禁。本节作为现有执行合同的追加裁定，覆盖 `04` 第 6 节及历史合同中把完整十族 R2 PASS 当作 Stage 3 或其他先行阶段准入前提的解释；冻结 `04`、候选、历史结果及其 hash 不改。

- Stage 3 必须完成第 2 节的实际候选验证、三角色制品、可复现性、安全、运行验证、准确 SHA 远端 required checks/不可绕过保护、registry 不可变性、签名验证和真实 manifest 绑定。对应 R2 的 `semantic_closure`、`candidate_identity`、`artifact_build`、`business_validation`、`security_supply_chain` 只按真实本阶段证据验收；不得用本地成功替代远端或权限依赖。现有 live-provider 要求不因本次裁定自动取消。
- Stage 3 实际 manifest 如实绑定现有证据及后续待办：未发生的后续阶段记录保留 `UNEXECUTED`（真实依赖未满足时为 `BLOCKED`），明确 owner 和应完成阶段，不填虚构 PASS。使用既有结果/矩阵表达阶段结论，不新增平行 validator、schema 或审批链。

| 后续 R2 family | 证据产生与验收边界（按冻结 `04`） |
| --- | --- |
| `runtime_staging` | Stage 4 隔离 staging runtime |
| `backup_recovery` | Stage 5 运行资格与恢复闭合 |
| `observability_canary` | Stage 5 的可观测性与 Stage 8 的有界 canary；canary 不前置到 Stage 6 |
| `independent_review` | Stage 6 独立候选资格审查；本地已有 review 不冒充最终资格 |
| `promotion_authority` | Stage 7 单独人类晋升授权；本裁定不是该授权 |

- 完整 stock R2 不删 family、不改阈值、不改返回值：Stage 3 运行它时，因上述后续项未执行而得到的非 PASS 照实保留，阶段验收单独判断本阶段条件，不宣称完整 R2 已通过。当前阶段的失败、遗漏、身份/hash 不符仍阻塞本阶段，不能统归为“后续项”。如现有 CI/检查把后续 family 错作先行阶段前置条件，应记录并在已有实现内做最小的阶段适用性修正及针对性验证；不得直接跳过 required job、改绿失败结果或删除最终 R2 门禁。本次文档更新不表示此类实现已修改。
- 各阶段只依赖已完成的前序阶段和本阶段明确授权：Stage 3 条件全满足并经监督验收后才准备 Stage 4；Stage 4 仍需单独 staging authority。Stage 6 以 Stage 0–5 及当时适用的资格证据审查，不要求尚未发生的 Stage 7 晋升或 Stage 8 canary PASS；Stage 8 仍必须具备 Stage 7 的有界授权。Stage 9 放量前必须补齐十族真实证据，并使完整 stock R2、候选身份及证据 hash 验证全部通过。此前任何阶段性 PASS 都不等于最终发布许可。
- 本次不授权 GitHub push/dispatch/规则修改、registry 发布、签名或 transparency 写入、live-provider 调用、staging/production 部署。无新输入不重建 r13x、不重跑已有效套件；仅合同顺序 blocker 已解除，其余实际缺口按原任务继续管理。

### 2.2 当前只完成本地交付（2026-09-13 最新用户指令）

用户明确要求“本地都弄好，发布推送授权等延后，密钥可以注入”。当前任务按本地范围收尾，不再等待外部发布授权：

- 完成本地源码/测试、安全扫描、三角色可复现制品及本地证明材料、生产配置的隔离本地运行和数据库迁移、可恢复制品保留；使用 r13x 已有效结果，不重跑已闭合工作。真实本地缺陷仍须修复，不能借范围调整略过。
- GitHub push/dispatch/required-check 或 ruleset 写入、registry 发布/promotion/immutability readback、实际签名与 transparency 写入、远端 staging/production 部署全部延后。它们记录为未执行的后续发布事项，不再列为当前本地交付的 blocker；第 2 节、第 2.1 节及第 5 节中的这些要求仍约束未来正式发布，不作为本轮本地收尾前提。
- 用户已允许密钥安全注入及本地有界真实 provider 验证。只使用用户指定或当前项目已有明确归属的环境变量/私密文件；不读取其他项目或账户寻找凭据，不回显或写入源码、日志、证据、镜像或聊天。先验证配置存在与隔离环境，再执行现有最小验证；无另行范围时最多一次最小真实 provider 请求，不批量调用、不提交生产或敏感数据。密钥不可用时只报告该输入缺口，不能将 scripted-provider 或 HTTP 200/degraded 冒充真实 provider PASS。
- 本地结果与运行/恢复说明复用现有记录：准确制品、测试归属、必要环境变量名、启动/停止及保留制品路径、未执行的发布事项。实际发布 manifest 尚缺外部证据时，保留其未完成状态；不伪造完整 R2 PASS，也不为本地交付另外搭建发布平台。
- 本地必需项完成即可回传本地范围 PASS 并由监督收尾，清楚区分“本地交付通过”和“正式 Stage 3 发布资格/完整 R2/生产许可未建立”。不得因外部事项后置而继续空等；也不得把本地收尾当作远端 Stage 4 部署授权。本次文档与范围调整不触发新候选或全量重测。

## 3. 最短执行路径与资源使用

1. 入场只确认当前 commit/tree、clean、必要输入 hash 与本次命令的工具/资源可用性，记录在既有主结果中。不另立入场报告，不默认重跑 Stage 1/2、fsck、R2 fixtures 或多路独立 review；发现具体漂移再检查受影响项。
2. 先跑已有廉价的导入/配置预检，修正解释器、候选路径、Compose plugin 和快照 mode。准备好的同一环境用于 focused 修复验证和相关 aggregate，避免每次另建 runner 后重新触发已修问题。测试环境差异如实记录，不修改生产校验来适配本机。
3. 对 r13l 尚缺的完整门禁按必需 selector 执行。已有同候选、同依赖/环境且有效的证据直接引用；按 subtree 复用的本地证据仅覆盖其已证明的范围，不能替代 required CI 精确 SHA 的真实运行。局部修复只复测受影响项；需要完整 aggregate 的门禁在相关修复稳定后集中完成，不因每个 receipt 或字段变化重跑全套。
4. 需要服务的工作仅使用可确认归属的独立本地容器/数据库；无依赖工作可并行，共享端口、数据库或 builder 的工作串行。隔离用现有 Compose project 名、临时目录、资源 ID 和 owner 记录表达，不以开发 lease 系统为前提。
5. 按三角色现有构建路径完成制品与第二次干净重建，集中生成所需 metadata/manifest，复用现有生成器。失败可修复重试，已通过路径没有新证据不扩测。不要为了通用失败恢复、任意平台兼容或“全部零 warning”扩写实现。
6. 保持一个主执行 runner；第二干净构建环境按需创建并顺序用于各角色，角色输入须隔离。并行确有独立需求时才增加 runner。不为每次重试复制整库或整套 Docker 数据；构建前检查可用空间，空间不足只阻塞相关构建。保留日志/receipt 和必要失败差异后清理无引用的 task-owned 临时输出，不能丢失唯一源码或失败证据。

Docker 当前环境已被用户清空；备份 `/Users/wangyiliang/Library/Containers/com.docker.docker/Data.backup-20260909-1506` 不得全量恢复、删除或用于接回旧数据库。阶段启动后可在可用的新 Docker 环境按需创建专属资源；引擎不可用时记录受影响 gate 并继续无依赖工作，不扩展成 Docker Desktop 修复/备份恢复项目。

持久证据写到本目录 `stage3-evidence/r13l/`；临时 runner/build 输出置于任务自建唯一临时目录。正式封存的证据不覆盖；开发中的结果表可更新，失败日志单独保留，不因每次状态更新新建 schema、successor 或索引版本。若完整性确有缺陷，修复现有工具的具体问题。

## 4. 自主修复与明确停止条件

- 普通工具、环境、命令和证据格式问题在原任务内自主修复，不逐项请求监督审核；确定性错误先修原因，网络瞬时错误才原样有限重试，不设僵硬的“最多两种方案”限制，也不盲目无限重跑。
- 修改产品、测试实现、workflow、Dockerfile/Compose、lockfile、migration 或配置时，由发现任务在已有授权范围内直接修复并做最小相关验证；不以修改文件类型为由自动退回 Stage 1/2。只有实际共享写冲突、跨模块职责或权限/语义选择才协调。稳定后仅在真实交付需要时统一更新冻结身份，机械身份交接不等待单独审批。历史冻结候选保持不变；证据按具体输入和依赖复用，不伪称旧 SHA 的运行属于新 SHA。
- 发现缺 remote SHA、推送/dispatch、registry/signing 写权限时，及时一次性列出确切目标、所需动作、影响 gate 和用户选择。能独立完成的已授权工作继续；它们完成后返回 `AWAITING_HUMAN_AUTHORITY`，不空转、不重复查询、不为绕过缺权构建替代平台。缺真实语义选择时同样明确提问，不能擅自裁决。
- 环境不可用且已无独立可完成工作时回传具体 `BLOCKED`；blocker 只属于实际依赖它的工作。Docker 空间/引擎问题不能追溯撤销已验收 Stage 1/2，也不能使未执行的 Stage 3 服务门禁变成 PASS。

## 5. 回传、验收与权限

用户调度明确（2026-09-10）：执行目标是完成整个 Stage 3，不是逐个监督分片。运行中只在有意义进展、计划变化或实际风险时回传；回传后自行继续下一项，不结束回合等待重新发放。此前监督消息中的“完成小包后等待发放”不再适用。普通工具、runner、fixture 与已授权修复不逐项验收。除用户明确暂停/停止外，正常结束只在完整阶段结果已实际送达监督，或确需用户新权限/语义选择且已完成所有可独立的授权工作时发生；后者必须说明精确目标、动作和受影响要求。阶段范围与权限不扩大，不创建新的 Goal 或调度框架。

继续使用现有结果格式、原始日志/JUnit 和一个证据索引；记录要求→结果/引用、准确命令/cwd、候选 commit/tree、工具/环境差异、退出码、制品 digest、未完成项和资源归属即可。重复 metadata 可引用同一记录，不为本文新建 validator/schema。warnings/skip/deselect 按现有输出保留、按原因归类；只有遗漏必需覆盖、违反阈值或真实行为风险才阻塞，不逐条生成修复任务。

`external_effects` 如实记录已授权本地资源写入和外部只读请求；判据为无未授权副作用，不再要求与允许操作冲突的空数组。secret、token、cookie、私钥和敏感正文不进入证据。

必须实际通过 `send_message_to_thread` 回传上述 Supervisor：`STAGE_RESULT`、候选身份、必需要求对应结果/证据、改动、验证范围、真实 blocker 和清理状态。可使用原状态词 `PASS / INPUT_DRIFT / REBUILD_REQUIRED / FAILED / BLOCKED / AWAITING_HUMAN_AUTHORITY / AWAITING_OBSERVATION_WINDOW`；普通进度回传不是审批点。

全部第 2 节要求及经第 2.1 节裁定的 `04` Stage 3 退出条件满足后才回传 `PASS`，随即停止扩测并等待阶段验收；该 PASS 不是完整 R2 PASS。仅本地工作完成就明确报告该范围及外部缺口，不降低本阶段实际条件。监督只审核阶段结果或真实权限/语义选择，不追加例行 fresh review 链。验收通过后才编写 Stage 4 合同；同 Stage 返工回到原任务。

不授权 push、workflow dispatch、remote/ruleset mutation、registry publish/promotion、signing/transparency-log 写入、staging/production 部署、live provider、production canonical write、external delivery、canary、cutover、authority transfer 或 legacy retirement。签名/远端写入需要明确目标授权；本地测试/build 许可不扩大为发布许可。
