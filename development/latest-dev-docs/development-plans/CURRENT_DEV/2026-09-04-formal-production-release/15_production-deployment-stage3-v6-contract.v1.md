# Stage 3 v6 候选验证与制品合同

- Status: `ACTIVE_STAGE3_V6 · NOT_AUTHORITY`
- Date: `2026-09-06`
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Executor: `01a074c0-5786-7121-8a0b-ffef1e32a2a9`
- Stage 1/2 repair task: `01a074e1-da0d-7a70-9c45-daff7b8bc9ad`
- Stage 4: `NOT_ADMITTED_NOT_WRITTEN`

## 1. 阶段审核与精确输入

Supervisor 接受 v6 的 exact-candidate 身份与声明的本地隔离 selector 结果，允许进入 Stage 3 验证与本地制品工作；这不是远端 CI、全环境测试、网络隔离证明或生产准入。

```text
candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v6
commit=909eb608e538b6427bcbacca974f1efb05fef611
tree=a60b795e509aa5dc479904a321fba32ed0ab9ab2
parent=88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6
strategy=REMEDIATION_INCLUSIVE_RELEASE
evidence_root=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6
candidate-manifest.v6.json=020ea3fe312fe5a21f5c064455fc7e2fb1d53440ca0a2dfa9bf115777c80ece1
closure.final.v6.json=d2f0607fbf29422f78887c5c72ac17af2d867e719044fa03a545ba19a1e30e73
stage2-record.final.v6.json=0a6555aca056084f3e7645d03b7adf04b3e4f2be49d52294e48f2b2a239f9a90
r1.final.v6.json=c0ed90b8d1253b0d8191cef46506d5ed436b74f34c6a4f8a0758de0b76ef8f2d
r2.pass.v6.json=0edca14b4177a63cb2046fb74ab01e1099d66277d5a778df91b6c7faedef9c76
r3.pass.v6.json=9f7bc679db5e6e481090e43c1c4ee9d59cfe29b9efa3d8e9fa470689cda61e03
```

已独立核验候选 HEAD/tree/parent、clean、non-shallow、无 alternates、Git fsck；closure 的 26 组显式文件/hash 配对均匹配。主候选与重放各为 1793 passed、52 subtests passed、2329 deselected、25 warnings、0 failed/errors/skipped；JUnit 的 tests=1845 包含 subtests，不得误写为 1845 个普通测试。

明确保留审核限制：`no-network-sitecustomize.v6.py` 只替换 `socket.getaddrinfo`，并未封禁所有 socket、子进程或直接 IP 网络连接。其 hash 为 `a993a3adcd7ef91bb95b766bc2239006e7d0312e0997e2b29c88a3c1dd0bebde`。因此 `NO_NETWORK_EFFECT` / 全面 socket isolation 未被该文件证明。Stage 2 通过限定为声明的 DNS 失败注入环境；Stage 3 必须分别记录真实 workflow 环境与测试隔离环境，不能把注入结果冒充未修改的远端 workflow 结果。历史失败日志保留，不覆盖 closure 或伪造网络观测。

## 2. 继承的阶段要求与本合同覆盖项

冻结 `04_production-deployment-stage-plan.v1.md`（SHA256 `d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa`）的 Stage 3 目标、要求、退出条件保持不变。

继承 `09_production-deployment-stage3-successor-contract.v1.md`（SHA256 `61d5b99ce8966b1bdb4eadf754ae03b7651026098b38da09dd46a69e773237be`）第 2、4–7、9–10 节的工作范围、门禁、证据字段和权限上限，所有当前候选 v4 引用替换为本合同 v6。历史 v3/v4/v5 及旧合同保持原字节，不能作为 v6 PASS。

旧第 1 节输入由本合同第 1 节与 v6 closure 内引用闭包替代；Stage 0/1 历史记录只是 predecessor，当前字节判定使用 closure 中 current-byte additive successors 和 intake remediation，不要求旧历史 hash 与新源码相等。前置检查只验证当前输入、有效 successor、工具与资源边界，不重新审核每次已完成修复。

## 3. 自主执行与固定边界

原 Stage 3 任务连续执行：candidate-bound 验证、backend/frontend/migration/architecture/law/security gates、专用本地 PostgreSQL 与 Docker smoke、三个角色的本地制品、第二干净环境重建、SBOM/provenance/scan，以及远端 required checks、registry、已有签名的只读核验。无依赖工作可并行，有共享资源或结果依赖的部分保持有序。

允许的新增写入仅为本目录 `stage3-evidence/v6/` 内 create-only evidence、唯一 `/private/tmp/mrw-stage3-v6-*` disposable clones/outputs，以及专属本地测试容器、镜像、缓存、测试数据库。数据库不得连接既有用户或生产实例；读依赖/漏洞数据、只读 GitHub/registry 查询不允许上传仓库、凭据或正文。不得从 dirty 主 checkout 构建 release artifact。

执行任务自主诊断、修复其临时工具/环境/证据格式、补测和重跑，取消旧第 8 节固定两次尝试及普通失败逐项报审要求。不以盲目相同重跑替代诊断。只在阶段结果或真实新增权限/用户语义选择时回传监督者。

需要修改 product/workflow/Docker/lockfile/migration/config 时，不得改 canonical v6 或冒充同一候选；将有界修复直接交回原 Stage 1/2 任务自主修复、验证和 create-only successor 冻结。Stage 3 可继续不依赖该修复的诊断，但 successor 的阶段身份须经 Supervisor 阶段验收后才能替代本合同输入；不能偷换候选。此流程复用原任务，不新建同 Stage 任务或每项修复合同。

权限缺口只阻断实际依赖它的门禁，继续完成可独立执行的本地/只读工作。未经授权的 push、workflow dispatch、registry publish、签名/透明日志写入不能执行；缺真实远端/registry/签名证据时，准确返回 `AWAITING_HUMAN_AUTHORITY` 或具体 blocker，不能降低 Stage 3 PASS 条件。

## 4. 阶段性回传与验收

按照继承合同的完整字段回传一次阶段结果和可验证 evidence index。每条测试/构建记录绑定 candidate commit/tree、准确命令、cwd、工具/依赖版本、环境差异、退出码、原始日志/JUnit与hash；保留失败尝试及 warning/skip/deselect。网络 guard 只按实际机制命名，不推断未观测效果。补充索引可 create-only，不改已有冻结记录。

Stage 3 PASS 仍要求所有规定测试与安全门禁、候选精确 SHA 的远端不可绕过 required checks、backend/frontend/migration immutable digests、重建证据、SBOM/provenance/scan、真实签名验证与 registry immutability、实际 release manifest 的 candidate-local R2 验证均符合冻结要求。R2 synthetic conformance、R3 静态通过或 Stage 2 本地 selector 均不替代这些事实。

同 Stage 返工继续本任务。只有 Stage 3 阶段性 PASS 经监督验收后才写 Stage 4 合同；本合同不授权 staging/production 部署。

```text
NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE
```
