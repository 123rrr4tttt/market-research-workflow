# MRW Stage 3 事件驱动 Supervisor 合同与进度账本（v1）

- Status: `ACTIVE_MUTABLE_STAGE_CONTRACT · NOT_AUTHORITY`
- Date: `2026-09-06`
- Supervisor task: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Stage: `STAGE_3_CANDIDATE_VALIDATION_AND_IMMUTABLE_ARTIFACTS`
- Strategy: `REMEDIATION_INCLUSIVE_RELEASE`
- Normative frozen plan: `04_production-deployment-stage-plan.v1.md`
- Frozen plan manifest: `05_production-deployment-stage-plan.freeze.v1.json`
- Predecessor mutable ledger: `06_production-deployment-stage-progress.v1.md`

本文件只定义和记录 Stage 3。Stage 3 worker 回传并经 Supervisor 独立验收前，不预写 Stage 4 合同。本文是 mutable、derived、non-authority 的执行投影，不修改、不替代也不扩张冻结计划；冲突时以 `00`、`01`、`02`、`04`、`05` 和更严格的权限边界为准。

本文中的 `READY`、`VERIFIED`、`PASS`、任务状态、报告、制品摘要和 CI readback 均不产生 deployment、candidate promotion、live provider、production canonical write、external delivery、canary、cutover、authority transfer、credential creation、legacy retirement 或 push 权限。

## 1. 当前权威输入与只读核验

### 1.1 冻结文档集合

```text
formal_release_plan_00=00_formal-production-release-development-plan.v1.md
formal_release_plan_00_sha256=97801ddbe46233429309f218cfcb183ade785ffd1a2d0872223907851ca95087
formal_release_gap_01=01_formal-production-release-gap-ledger.v1.json
formal_release_gap_01_sha256=21df93d7c9dc1ac3cc77a9a449f3c37527001f0716551ce34db032c7c93754a0
formal_release_freeze_02=02_formal-production-release-development.freeze.v1.json
formal_release_progress_03=03_formal-production-release-progress.v1.md
production_stage_plan_04=04_production-deployment-stage-plan.v1.md
production_stage_plan_04_sha256=d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa
production_stage_plan_04_bytes=24713
production_stage_plan_04_lines=420
production_stage_freeze_05=05_production-deployment-stage-plan.freeze.v1.json
production_stage_freeze_05_sha256=06d2ec76f7c59973997311ac7ae416005ae0b9c7784598b11127e436dcf8a2aa
production_stage_progress_06=06_production-deployment-stage-progress.v1.md
freeze_exact_bytes=PASS
```

必要的直接引用合同已读：successor migration development contract、historical production runbook、security checklist、monitoring and rollback plan。后三者分别保持 `DOCUMENTED_NOT_EXECUTED`、`CHECKLIST_DOCUMENTED`、`RECOMMENDATION_NOT_IMPLEMENTED` 的历史/文档边界，不得覆盖 Stage 1–2 当前 exact-bound evidence，也不得充当 Stage 3 PASS。

### 1.2 Stage 0–2 锚点

```text
stage0_status=COMPLETE_NOT_PRODUCTION_QUALIFIED
stage0_record=stage0-evidence/functorial-refactor-completion.v4.json
stage0_record_sha256=4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda
stage0_record_status=FUNCTORIAL_REFACTOR_COMPLETE_NOT_PRODUCTION_QUALIFIED

stage1_status=COMPLETE_NOT_PRODUCTION_QUALIFIED
stage1_record=stage1-evidence/production-contract-implementation.v1.json
stage1_record_sha256=3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31
stage1_record_status=PRODUCTION_CONTRACT_IMPLEMENTED_NOT_AUTHORITY
stage1_independent_review=stage1-evidence/independent-review.v1.md
stage1_independent_review_sha256=10117a7c8c4eec19c33e3ad841c99fb301c43fcda71f8d7addbde4070646f72c
stage1_exact_candidate_record_check=PASS

stage2_status=COMPLETE_NOT_PRODUCTION_QUALIFIED
candidate_commit=f8d84afc2784cf91784da957e353e2b0c0d6952c
candidate_tree=1be3dcbc009332ec225297d1b94430862287d816
candidate_parent=88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6
candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v3
candidate_manifest=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/candidate-manifest.v3.json
candidate_manifest_entries=6134
candidate_manifest_sha256=a95e4103dfa3743c6a603079f838d48a20665b38afe7fa2a9b2623ab443522bf
candidate_closure=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/closure.final.v3.json
candidate_closure_sha256=53497a752a9207b4dc54f8a5ab7e8af23d3f937a82fb71c8e8bc3092fc410808
candidate_r1=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/r1.final.v3.json
candidate_r1_sha256=fdd6053faeada17b62c050207078ff5944a3c759eb5d6183a43ac4f74cc4774e
candidate_record=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/stage2-record.final.v3.json
candidate_record_sha256=46d0df3f320619508130f87f6f8d60baba6c6080918293f3d021fbe7e26fb312
candidate_live_head_tree_check=PASS
candidate_live_status=tracked_0:untracked_0
candidate_live_r1=PASS
candidate_git_fsck=PASS
```

主 checkout 的 `HEAD/tree` 为 `3706655f372f6d34fc62683551b8c3d1f4ff8146` / `5840bf9ba906c49f70020d226c54446f4ba5aa33`，并含大量用户拥有的脏状态。它不是 candidate。Stage 3 不得从主 checkout 构建 release artifact；可能产生 cache、install 或 build output 的工作必须基于 Stage 2 candidate 创建 disposable standalone clone。

Stage 0 独立接受在 `06` 当前账本中记录为 `ACCEPT`，有界仓库集合中没有单独 Stage 0 review 文件。Stage 1 exact-byte checker 已在隔离 candidate 上重新验证 Stage 0 completion、Stage 1 record、冻结计划和 receipt bindings。该边界不把 `06` 提升为 authority；后续 Stage 6 仍须执行新的独立 exact-candidate review。

## 2. Stage 3 状态机

```text
READY
  -> DISPATCHED          create_thread(project local)
  -> REPORTED            receive structured STAGE_RESULT
  -> VERIFIED            Supervisor reopens evidence and runs minimal checks
  -> READY_STAGE_4       only after Stage 3 PASS is independently verified
```

旁路状态：

```text
BLOCKED
FAILED
REBUILD_REQUIRED
AWAITING_HUMAN_AUTHORITY
AWAITING_OBSERVATION_WINDOW
```

状态语义：

- `READY`：本合同前置条件经当前只读核验通过，且不存在不明 active writer 或 Git lock。
- `DISPATCHED`：一个用户可见的新 Codex task 已用本项目 `local` 环境创建。禁止 worktree 或 subagent 替代。
- `REPORTED`：收到完整 `STAGE_RESULT`。`turnCompleted`、`idle`、普通 final answer 或 worker 自称完成只触发验收，不等于 PASS。
- `VERIFIED`：Supervisor 重开原始证据，核对 SHA-256、candidate/artifact identity、远端 readback 和 authority ceiling，并运行最小只读/确定性验收。
- `BLOCKED`：明确环境、remote、registry、toolchain 或依赖 blocker；不能提升为 PASS。
- `FAILED`：执行失败且失败归属明确；同一失败最多重试两种有实质差异的方案。
- `REBUILD_REQUIRED`：任何修复会改变 candidate 所绑定的源码、workflow、Docker、migration、lockfile、配置或 Stage 2 输入；必须停机并生成 additive successor candidate。
- `AWAITING_HUMAN_AUTHORITY`：所需外部持久写、registry publish、signing、workflow dispatch 或权限只能由真实人类/组织 authority 授予。
- `AWAITING_OBSERVATION_WINDOW`：Stage 3 通常不依赖 soak 窗口；若外部扫描/attestation 服务具有不可压缩等待期，须记录真实开始/结束时间，禁止用测试或轮询压缩。

本 Supervisor 采用事件驱动循环：worker 回传 -> Supervisor 独立验收 -> 才编写 Stage 4 合同。它不使用 Goal 作为阶段事实、完成信号或等待机制。修正前误建的 Goal 已废弃且不再读取或更新。

## 3. Stage 3 worker 完整合同

### Objective

让 Stage 2 exact candidate 的完整验证成为 candidate-bound evidence；核验远端 required checks 的不可绕过性；只从同一 candidate 构建可验证、不可覆盖、可回退的 backend、frontend 和 migration artifacts，并产生 SBOM、provenance、漏洞扫描、签名/验证与 reproducibility evidence。

### Frozen inputs

- candidate commit `f8d84afc2784cf91784da957e353e2b0c0d6952c`；
- candidate tree `1be3dcbc009332ec225297d1b94430862287d816`；
- candidate manifest/closure/R1/record 路径和 SHA-256，见第 1.2 节；
- Stage 0 completion、Stage 1 implementation/review exact-bound records；
- `04` frozen plan 和 `05` freeze manifest；
- strategy `REMEDIATION_INCLUSIVE_RELEASE`。

任何输入 byte、digest、commit、tree 或策略变化都会使本合同失效。

### Preconditions

1. candidate root 存在且 `git status --porcelain=v1 --untracked-files=all` 为空；
2. `git rev-parse HEAD HEAD^{tree}` 精确匹配冻结 commit/tree；
3. fresh R1 为 `PASS`；
4. Stage 1 record checker 在 candidate 上为 `PASS`；
5. `04`/`05`、Stage 0/1 records 和 Stage 2 evidence SHA-256 未漂移；
6. 没有不明 active project writer、Git lock 或同 Stage worker；
7. remote、registry、signing 或 workflow action 的持久 effect 均有独立权限；无权限时先完成可做的 read-only/local evidence，再返回 `AWAITING_HUMAN_AUTHORITY`。

### Allowed reads

- Stage 2 candidate 的全部 tracked bytes；
- Stage 0–2 records、receipts、manifest、closure 和 R1；
- 当前本地 build/test toolchain 及公开版本信息；
- read-only GitHub branch-protection、ruleset、check-run、workflow/run API；
- read-only artifact registry metadata、签名验证 metadata 和公开漏洞数据库；
- 为归属 warning/skip/failure 所需的相关测试与配置。

### Allowed writes

- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/` 内 additive create-only evidence；
- `/private/tmp/mrw-stage3-*` disposable standalone clones、logs 和 build outputs；
- 本地 disposable container/image/build cache，只能使用 Stage 3 唯一命名并在回传中列出；
- 经人类明确授权后，合同精确指定的非生产 artifact registry namespace 或 workflow dispatch。授权前不得执行。

worker 不得修改本合同、`00`–`06`、canonical candidate root 或任何产品/配置输入。

### Forbidden actions

- 从主 dirty checkout 构建或打包 candidate artifact；
- 修改 canonical candidate checkout，或运行会改变 tracked/untracked candidate 状态的命令；
- 修改源码、workflow、Dockerfile、compose、migration、lockfile、版本、production config、Stage 0/1 record 或 Stage 2 evidence；
- `git reset`、`clean`、`stash`、`rebase`、commit、tag、push、force-push、remote branch/ruleset mutation；
- registry publish/promotion、创建签名密钥、keyless transparency-log 写入、workflow dispatch，除非有显式人类授权；
- production/staging deploy、生产 secret、live provider、production canonical write、external delivery、canary、cutover、authority transfer 或 legacy retirement；
- 覆盖同名 artifact/evidence，隐藏 warning/skip/deselect/failure，或用历史 candidate evidence 冒充当前运行。

### Authority and effect boundary

- 本地只读验证、disposable clone tests/builds、local OCI archive 和 read-only remote readback 可在本合同内执行。
- GitHub workflow dispatch、registry write/promotion、签名服务写入、credential/key creation 或任何外部持久 mutation 不由本合同授权。
- 如果 Stage 3 PASS 必需的 remote/registry/signing 证据缺权限，worker 必须返回 `AWAITING_HUMAN_AUTHORITY`，不得降格 gate 或伪造本地替代物。
- 所有 Stage 3 manifest/report 必须 `authoritative=false`；build/test/runtime success 不产生 candidate promotion 或 production authority。

### Acceptance checks

1. 对 exact candidate 重新运行 R1、R2、R3；
2. backend unit、integration、core-business、schema/migration、successor-runtime 完整门禁；
3. architecture、registry、law、exact-byte、negative/failure 门禁；
4. PostgreSQL opt-in suites 使用专用 disposable DB，teardown residue 为 0；
5. frontend frozen install、lint、typecheck、build、component/e2e；
6. Bandit、`pip-audit`、gitleaks、frontend dependency audit 和 image scan；
7. Docker build 与 full-stack smoke，production compose 无 source bind mount；
8. GitHub live readback 证明 required workflow/jobs 绑定 candidate SHA、全部 required conclusion 为 PASS 且不可绕过；
9. 所有 base image 和 compose image 由 digest 固定，无 production `latest`；
10. backend、frontend、migration runner 分别产生 immutable digest；
11. 两个 standalone clean build 环境针对同一 candidate 重建并比较 digest；若平台差异阻止 bit-for-bit，明确差异域并提供签名 provenance 与运行等价证据，不得宣称完全可复现；
12. 生成并验证 SBOM、build provenance、vulnerability result、signature/attestation；
13. registry artifact 使用不可变 digest 或不可覆盖 namespace，并有 readback；
14. release manifest 绑定 candidate commit/tree、artifact digests、build/run identity、toolchain/platform 和 evidence hashes；
15. warning、skip、deselect、environment block、native abort、scanner exception 全部逐项归属，不得从聚合中消失；
16. disposable resources 清理完成，或 retained evidence 明确 owner、路径、理由和恢复方式。

`PASS` 必须满足全部 required checks。只完成本地 build/tests 或只证明 workflow 文本存在，均不足以 PASS。

### Evidence schema

主记录 schema：`mrw.formal_release.stage3.candidate_artifact.v1`。至少包含：

```text
schema_version
stage_id
status
authoritative=false
candidate_commit
candidate_tree
input_digests
toolchain_and_platforms
ci_run_head_sha
required_jobs_and_conclusions
remote_enforcement_readback
test_families_and_exact_results
warning_skip_deselect_inventory
artifact_names_and_immutable_digests
reproducibility_class
declared_platform_differences
sbom_refs_and_sha256
provenance_refs_and_sha256
signature_verification
security_scan_results
registry_immutability_readback
external_effects
cleanup_and_retained_resources
open_failures
authority_ceiling
observed_at
```

每个 `PASS` evidence ref 与 SHA-256 位置配对；路径必须存在；ID 唯一；所有 JSON 根类型、schema 和 status vocabulary 可确定性解析。secret、token、cookie、私钥和敏感正文不得进入 evidence。

### Stop rules

任一条件触发即停止扩大工作面并回传当前证据：

- candidate/plan/record/evidence identity mismatch；
- candidate root 变脏或出现 Git object/lock 异常；
- required gate 失败或 required job 不可证明远端强制；
- candidate SHA 不存在于可核验 remote，且合同禁止 push；
- registry/signing/workflow dispatch 需要未授予的权限；
- artifact digest 与 provenance/candidate 不一致，或 registry 可覆盖；
- scanner 有未裁决 blocker，或 warning/skip 无法归属；
- 构建/测试修复需要改变 frozen inputs；
- 任何 staging/production/live/canonical/canary/cutover effect 风险。

### Rollback and recovery

- 删除或隔离 `/private/tmp/mrw-stage3-*` disposable clones 和 Stage 3 唯一 cache；
- 本地镜像只按 Stage 3 精确标签/ID 清理，不影响既有服务；
- 保留失败日志、scanner 输出和摘要，生成 create-only negative evidence；
- 任何已发生外部持久写必须记录 remote identity、owner、撤销/恢复路径和当前状态；worker 不得猜测或自动扩大 cleanup；
- candidate root 和历史 evidence 永不覆盖。

### Timeout and retry

- 同一失败最多尝试两种有实质差异的方案；无新证据即返回 blocker；
- 长 suite/build 只允许一次基于相同输入、原因明确的重跑；不得通过选择性子集把失败改写为 PASS；
- 网络瞬时失败可 bounded retry，记录次数/退避/最终结果；
- 缺 remote/registry/signing authority 不能通过 retry 解决；
- 达到可用墙钟或资源上限时，回传已经完成的证据、未执行项和真实 blocker，不持续空转。

### Completion signal

worker 必须在自身任务给出 final answer，并调用 `send_message_to_thread` 向 Supervisor task `01a0748b-be3b-7da2-9cb2-4160756bf10b` 发送：

```text
STAGE_RESULT: PASS | BLOCKED | FAILED | REBUILD_REQUIRED | AWAITING_HUMAN_AUTHORITY | AWAITING_OBSERVATION_WINDOW
stage_id: STAGE_3
input_commit:
input_tree:
input_digests:
changed_paths:
evidence_paths_and_sha256:
checks_run_and_exact_results:
external_effects:
cleanup_and_recovery_status:
residual_blockers:
authority_ceiling:
recommended_next_action:
```

### Next-stage eligibility

只有以下条件全部满足并由 Supervisor 独立记为 `VERIFIED`，才允许编写 Stage 4 合同：

- exact candidate identity 未变化；
- required CI live enforcement、run/job conclusions 和 candidate SHA 精确绑定；
- immutable artifact digests、SBOM、provenance、signature verification、security scans 和 registry immutability readback 完整；
- reproducibility 或明确的平台差异替代证据通过；
- required warning/skip/deselect/negative 状态无隐藏；
- cleanup/recovery 闭合；
- authority ceiling 仍明确为非部署、非生产。

若 worker 仅返回 `BLOCKED`、`FAILED`、`AWAITING_HUMAN_AUTHORITY` 或 `AWAITING_OBSERVATION_WINDOW`，Supervisor 不编写 Stage 4 合同；在原 Stage 3 worker 上继续补证或等待事件。

### REBUILD_REQUIRED

出现下列任一情况必须返回 `REBUILD_REQUIRED`：

- 修复需改变 source、workflow、Dockerfile/compose、migration、lockfile、production config 或 version identity；
- Stage 0/1 completion/evidence record 或 Stage 2 manifest/input closure 需修改；
- candidate 中缺少 required file、test、workflow、build definition 或 static security closure；
- artifact 无法从 candidate 重现的原因位于 candidate bytes；
- Stage 3 发现 Stage 1 的实现合同实质不成立。

`REBUILD_REQUIRED` 必须保留当前 candidate/evidence 为历史对象，指出最早需返回的 Stage、准确 changed surface 和 successor candidate 所需 rebind；不得就地修补 Stage 2 candidate。

## 4. Supervisor 独立验收合同

收到回传后，Supervisor 至少执行：

1. 重新读取本合同和 `04`/`05`，重算 digest/bytes/lines；
2. 重新读取 Stage 2 record/manifest/closure/R1，核对 SHA-256；
3. 在 canonical candidate root 只读核对 HEAD/tree/status，并 fresh R1；
4. 检查 worker evidence 路径存在、SHA-256、JSON/manifest schema、必填字段、唯一 ID、引用配对和状态词表；
5. 独立核对 remote required-check/ruleset/readback 是否真绑定 candidate SHA；
6. 独立核对 artifact digest、SBOM、provenance、signature 与 registry immutability readback；
7. 检查 warning/skip/deselect、external effects、cleanup 和 authority ceiling；
8. 只运行合同规定的最小确定性/focused checker，不重复 worker 的全部长 suite；
9. P0、identity、authority、recovery、hidden failure 或 frozen-input drift 一律不验收；
10. 验收通过才更新为 `VERIFIED` 并开始编写 Stage 4 合同。

同一 Stage 的小修正通过 `send_message_to_thread` 返回原 worker。worker 的 `turnCompleted`、普通 final answer 或自报 PASS 不是 Supervisor PASS。

## 5. 当前事件账本

```text
supervisor_mode=EVENT_DRIVEN_NO_GOAL
supervisor_task=01a0748b-be3b-7da2-9cb2-4160756bf10b
current_stage=STAGE_3
current_state=STAGE_3_V4_REBUILD_REQUIRED_INDEPENDENTLY_VERIFIED
current_worker_task=01a07498-e35e-7163-8c53-5891979febcd
dispatched_at=2026-09-06T02:43:04Z
reported_at=2026-09-06T02:49:00Z
verified_at=2026-09-06T02:57:42Z
last_report=REBUILD_REQUIRED:stage3.required_r2_bytes_absent
last_verification=ACCEPT_REBUILD_REQUIRED:CANDIDATE_EXACT_AND_CLEAN:R1_PASS:STAGE1_RECORD_PASS:R2_REQUIRED_PATHS_ABSENT:CI_DAG_DEPENDS_ON_ABSENT_TEST
successor_return_contract=08_stage1-stage2-additive-successor-return-contract.v1.md
successor_return_contract_sha256=77db632919118f7a37924634453f38eae260261de78ac4f063743db818325dc5
successor_return_state=PASS_INDEPENDENTLY_VERIFIED
successor_return_worker_task=01a074aa-72d1-7943-83a1-1745ecc8ef61
successor_return_dispatched_at=2026-09-06T03:02:22Z
successor_return_verified_at=2026-09-06T03:23:20Z
successor_candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v4
successor_commit=e1aa59708a22e4238c4d9beaf7b7bd2d2095d483
successor_tree=d2003fbb8e54c8dd743fa4e84907a8a978ef5107
successor_return_verification=ACCEPT:6147_RAW_DELTA_EXACT:R1_R2_R3_PASS:STAGE1_HISTORICAL_AND_REMEDIATION_CHECKERS_PASS:REPLAY_EQUAL:OBJECT_STORE_ISOLATED:V3_UNCHANGED
stage3_successor_contract=09_production-deployment-stage3-successor-contract.v1.md
stage3_successor_contract_sha256=61d5b99ce8966b1bdb4eadf754ae03b7651026098b38da09dd46a69e773237be
stage3_successor_state=REBUILD_REQUIRED_INDEPENDENTLY_VERIFIED
stage3_successor_worker_task=01a074c0-5786-7121-8a0b-ffef1e32a2a9
stage3_successor_dispatched_at=2026-09-06T03:26:04Z
stage3_successor_verified_at=2026-09-06T03:59:46Z
stage3_successor_failure=stage3.v4.missing_mrw_functorial_core_modules
stage3_successor_evidence_index_sha256=fbe1914ff111879edd1d1f5db02b7322232bdfa0bf05e752581ce2ea53992926
v5_return_contract=10_stage1-stage2-source-and-static-closure-return-contract.v1.md
v5_return_contract_sha256=0c20328727fdefca6a3161e212490a2043efeee17e4bffc854f8ee17847cdd6b
v5_return_state=DISPATCHED
v5_return_worker_task=01a074e1-da0d-7a70-9c45-daff7b8bc9ad
v5_return_dispatched_at=2026-09-06T04:02:43Z
active_project_writer=STAGE_1_STAGE_2_V5_RETURN_WORKER_ONLY
next_action=WAIT_FOR_STRUCTURED_RETURN_RESULT_THEN_VERIFY
authority_ceiling=NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_CANARY_NO_CUTOVER_NO_PUSH_NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE
```

Stage 3 worker 已回传并处于 `idle`；主 checkout 与 canonical candidate 均未发现 Git lock。Supervisor 已按第 4 节完成独立验收并接受 `REBUILD_REQUIRED`。本状态不撤销 Stage 2 v3 的历史完成记录，但禁止继续把该候选作为 Stage 3 可验收输入。

## 6. Stage 3 独立验收结果

```text
worker_result=REBUILD_REQUIRED
worker_task_status=IDLE_AFTER_COMPLETED_TURN
failure_id=stage3.required_r2_bytes_absent
candidate_commit=f8d84afc2784cf91784da957e353e2b0c0d6952c
candidate_tree=1be3dcbc009332ec225297d1b94430862287d816
candidate_status=tracked_0:untracked_0
candidate_git_fsck=PASS
fresh_r1=PASS:5_findings
fresh_stage1_exact_byte_record_check=PASS
candidate_required_path_1=scripts/formal_release/check_release_evidence.py:ABSENT_FROM_HEAD
candidate_required_path_2=tests/formal_release/test_check_release_evidence.py:ABSENT_FROM_HEAD
required_ci_job=evidence-validation-check:CALLS_ABSENT_TEST
dependent_ci_job_1=artifact-metadata-check:NEEDS_evidence-validation-check
dependent_ci_job_2=required-convergence-check:NEEDS_evidence-validation-check
main_checkout_path_status=both_untracked_user_owned_not_candidate_evidence
stage4_eligibility=NO
```

验收证据：

```text
stage3_preconditions_evidence=stage3-evidence/stage3-preconditions-rebuild-required.v1.json
stage3_preconditions_evidence_sha256=4f63e5cf764d7aad4fcb3f18f422a7fa2d4195ac8066b1d19196137d0cffcf2a
stage3_candidate_artifact_evidence=stage3-evidence/stage3-candidate-artifact.v1.json
stage3_candidate_artifact_evidence_sha256=f2075bf4742ea711be6402204be5c54d54f8f8b5446eab952c2d2f34d1b5965e
```

两个 JSON 均可解析，schema、status、candidate identity、input digest、failure owner、cleanup、external effects 和 authority ceiling 与现场只读核验一致。冻结 `00`–`06`、Stage 0/1 records 及 Stage 2 manifest/closure/R1/record 的 SHA-256 均未漂移。

因此，本轮不编写 Stage 4 合同。下一工作必须依据 additive return contract 回到 Stage 1，把 R2 checker/test 纳入正式、可验证、candidate-bound 的输入闭包，再生成新的 Stage 2 successor commit/tree/manifest/closure/R1/record。不得修改或覆盖 v3 candidate 与 v3 evidence。

## 7. Stage 1/2 additive successor 独立验收结果

```text
return_worker_task=01a074aa-72d1-7943-83a1-1745ecc8ef61
return_worker_status=IDLE_AFTER_COMPLETED_TURN
return_result=PASS_INDEPENDENTLY_VERIFIED
stage1_remediation_record=stage1-successor-evidence/r2-remediation.v1/stage1-r2-remediation-record.v1.json
stage1_remediation_record_sha256=97203433ca9dcf7f36e98f4dca2461d60f0159515f002127c153a5e061f74efe
candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v4
candidate_commit=e1aa59708a22e4238c4d9beaf7b7bd2d2095d483
candidate_tree=d2003fbb8e54c8dd743fa4e84907a8a978ef5107
candidate_parent=88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6
candidate_status=tracked_0:untracked_0
manifest_entries=6147
raw_delta_paths=6147
raw_delta_manifest_equality=PASS
fresh_r1=PASS:5_findings
fresh_r2_and_remediation_focused=PASS:12
fresh_workflow_contract=PASS:10
fresh_r3=PASS:12_findings
historical_stage1_checker=PASS
stage1_remediation_checker=PASS
replay=PASS:same_commit_and_tree
object_store_isolation=PASS:no_shallow:no_alternates:no_shared_object_inode
git_fsck=PASS
historical_v3_unchanged=PASS
git_locks=NONE
external_effects=[]
stage4_eligibility=NO
```

v4 evidence exact hashes：

```text
manifest_sha256=abc012b5c114d2d280db5bc5fc24c5591caa5bacc76840b154ec848dca5ae8b0
closure_sha256=6e3cf6dfd3ac7c336e81ab5c9b2e310373de7b981edce88109261ac031575c18
r1_sha256=79f7301e0c1e08553982ccc5c88f5854113825c81019ef6244da6bbd025260f0
r2_sha256=8e37eee14ea2eb865a048f57fec7ca55346da642509dc65ac99899b3d69a87ce
r3_sha256=86c67a4532a5a125f65c8f7405bd2b4b775472112e1577d85355fe6001ff5383
stage2_record_sha256=e2797d157c0a97f70b382d6ee6197bbcb073f6e55ac6ced5abe6946318345891
primary_materialization_sha256=76256addd9668a7d3a466fff2b2c98ab76be9e87ad9236878c8d483c5de0161b
replay_materialization_sha256=53aada9354d0c4410b7b359cd05b76e03899225f116107862e8fadd730beb6e6
```

回返过程中的两条 warning 已保留并完成归属：第一次临时 clone 继承 shallow 状态后在 materialization 前 fail-closed；第二次以 v3 为种子的 standalone clone 先把遗留 candidate ref 恢复到 manifest base precondition，再执行 materialization。两者均未污染最终 v4、v3 或主 checkout，也未产生 residual resource。

## 8. Stage 3 v4 successor 独立验收结果

```text
worker_task=01a074c0-5786-7121-8a0b-ffef1e32a2a9
worker_status=IDLE_AFTER_COMPLETED_TURN
worker_result=REBUILD_REQUIRED
supervisor_decision=ACCEPT_REBUILD_REQUIRED
failure_id=stage3.v4.missing_mrw_functorial_core_modules
candidate_commit=e1aa59708a22e4238c4d9beaf7b7bd2d2095d483
candidate_tree=d2003fbb8e54c8dd743fa4e84907a8a978ef5107
candidate_status=tracked_0:untracked_0
candidate_git_fsck=PASS
candidate_git_locks=NONE
required_absent_1=src/mrw_functorial_kit/core/w07_semantics.py
required_absent_2=src/mrw_functorial_kit/core/agent_service_semantics.py
candidate_consumers=7
minimal_candidate_import=FAIL:ModuleNotFoundError
backend_unit_attempt_2=FAIL:exit_2:292_collection_errors:1_skip:585_deselects
fresh_r1_r2_r3=PASS
historical_stage1_checker=PASS
stage1_r2_remediation_checker=PASS
actual_release_evidence_r2=FAIL_EXPECTED:formal_rc_ready_false
remote_readback=UNEXECUTED_EARLY_STOP
artifacts=[]
external_effects=[]
cleanup=PASS:no_retained_resources
stage4_eligibility=NO
```

当前 evidence index：

```text
path=stage3-evidence/v4/evidence-index.v2.json
sha256=fbe1914ff111879edd1d1f5db02b7322232bdfa0bf05e752581ce2ea53992926
indexed_current_and_superseded_hashes=ALL_MATCH
```

Supervisor 重算 current records、receipts 和 superseded create-only evidence 的全部 index hashes；重开失败日志；在 v4 上核对缺失路径和 7 个实际 import consumer；并独立运行最小 import，复现 `No module named 'mrw_functorial_kit.core.w07_semantics'`。主 checkout 中两个同名文件分别为 `??`，SHA-256 为 `5afc74cc...6b29fe4` 与 `c23c3d7c...e3a32dd`；相关语义、registry 和 backend functorial-debt focused tests 为 `61 passed, 2 warnings`。这些主 checkout 结果只证明存在可修复输入，不改变 v4 failure。

同时，Supervisor 静态复核确认 v4 required workflow 尚未建立独立 frontend component/e2e required execution、frontend dependency audit、image scan，以及分别绑定 backend/frontend/migration runner 的 immutable artifact digests。它们不是本次 early-stop 的直接失败原因，但属于下一次 candidate freeze 前应闭合的已知 Stage 1 输入缺口；不得留待新 candidate 后重复发现。

因此 v4 与其 Stage 3 evidence 保留为 immutable history。下一工作回到 Stage 1 source/static closure，并在通过后生成 additive Stage 2 v5；不得就地复制文件到 v4，不得进入 Stage 4。

## 9. Stage 线程复用规则（用户指令，后续回传起生效）

```text
effective_after_next_return=true
routing_policy=ONE_CANONICAL_THREAD_PER_STAGE
same_stage_rework=SEND_MESSAGE_TO_EXISTING_STAGE_THREAD
same_stage_supplemental_evidence=SEND_MESSAGE_TO_EXISTING_STAGE_THREAD
same_stage_retry=SEND_MESSAGE_TO_EXISTING_STAGE_THREAD
create_thread_allowed_only_for=FIRST_ENTRY_INTO_A_DIFFERENT_STAGE_WITH_NO_EXISTING_THREAD
current_v5_return_thread_exception=KEEP_AS_DISPATCHED
current_v5_return_thread=01a074e1-da0d-7a70-9c45-daff7b8bc9ad
canonical_stage3_thread_from_next_return=01a074c0-5786-7121-8a0b-ffef1e32a2a9
stage4_thread=CREATE_ON_FIRST_ELIGIBLE_ENTRY_ONLY_THEN_REUSE
```

从当前 v5 回返任务的下一次回传开始，同一 Stage 的反工、补证、等待后续执行和重试，均通过 `send_message_to_thread` 发回该 Stage 已有任务，不再调用 `create_thread`。只有首次进入一个尚无既有任务的不同 Stage，才创建一次新任务；此后该 Stage 也固定复用。当前已经派发的 v5 回返任务按用户指令作为一次性历史例外，不迁移、不重建。
