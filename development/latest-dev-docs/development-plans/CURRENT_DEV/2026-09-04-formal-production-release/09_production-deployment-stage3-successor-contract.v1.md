# MRW Stage 3 successor 执行合同（v1）

- Status: `ACTIVE_STAGE_3_SUCCESSOR_CONTRACT · NOT_AUTHORITY`
- Date: `2026-09-06`
- Supervisor task: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Stage: `STAGE_3_CANDIDATE_VALIDATION_AND_IMMUTABLE_ARTIFACTS`
- Candidate generation: `V4_ADDITIVE_SUCCESSOR`
- Strategy: `REMEDIATION_INCLUSIVE_RELEASE`
- Stage 4: `NOT_WRITTEN_NOT_ELIGIBLE`

本合同只定义绑定 v4 successor candidate 的 Stage 3。它取代 v3 Stage 3 尝试的执行输入，但不修改 `07` 中的历史 `REBUILD_REQUIRED` 记录。Stage 3 worker 回传并经 Supervisor 独立验收前，不编写 Stage 4 合同。

本文及其任何 `PASS`、artifact、manifest、CI readback、SBOM、provenance、scan、signature verification 或 reproducibility 结论均为 derived、non-authority evidence，不产生 deployment、live provider、production canonical write、external delivery、canary、cutover、authority transfer、legacy retirement、push、remote mutation、registry write 或 signing write 权限。

## 1. Exact frozen inputs

### 1.1 Candidate identity

```text
candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v4
candidate_commit=e1aa59708a22e4238c4d9beaf7b7bd2d2095d483
candidate_tree=d2003fbb8e54c8dd743fa4e84907a8a978ef5107
candidate_parent=88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6
candidate_strategy=REMEDIATION_INCLUSIVE_RELEASE
candidate_status_at_acceptance=tracked_0:untracked_0
candidate_shallow=false
candidate_alternates=false
candidate_shared_object_inodes=0
candidate_git_fsck=PASS
```

### 1.2 Candidate evidence

```text
candidate_manifest=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/candidate-manifest.v4.json
candidate_manifest_sha256=abc012b5c114d2d280db5bc5fc24c5591caa5bacc76840b154ec848dca5ae8b0
candidate_manifest_entries=6147
candidate_closure=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/closure.final.v4.json
candidate_closure_sha256=6e3cf6dfd3ac7c336e81ab5c9b2e310373de7b981edce88109261ac031575c18
candidate_r1=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/r1.final.v4.json
candidate_r1_sha256=79f7301e0c1e08553982ccc5c88f5854113825c81019ef6244da6bbd025260f0
candidate_r2=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/r2.pass.v4.json
candidate_r2_sha256=8e37eee14ea2eb865a048f57fec7ca55346da642509dc65ac99899b3d69a87ce
candidate_r3=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/r3.pass.v4.json
candidate_r3_sha256=86c67a4532a5a125f65c8f7405bd2b4b775472112e1577d85355fe6001ff5383
candidate_record=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/stage2-record.final.v4.json
candidate_record_sha256=e2797d157c0a97f70b382d6ee6197bbcb073f6e55ac6ced5abe6946318345891
primary_materialization=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/candidate-primary.materialization.v4.json
primary_materialization_sha256=76256addd9668a7d3a466fff2b2c98ab76be9e87ad9236878c8d483c5de0161b
replay_materialization=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4/candidate-replay.materialization.v4.json
replay_materialization_sha256=53aada9354d0c4410b7b359cd05b76e03899225f116107862e8fadd730beb6e6
```

`candidate_r2` 只证明 R2 validator 在 v4 中存在并通过 conformance/fail-closed fixture；它不是实际 Stage 3 release-evidence manifest，也不证明 production readiness。Stage 3 必须生成绑定真实 candidate/artifact/test/remote 状态的记录，不能把 synthetic fixture 当成 release evidence。

### 1.3 Stage 0/1 and return lineage

```text
stage0_completion=stage0-evidence/functorial-refactor-completion.v4.json
stage0_completion_sha256=4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda
stage1_historical_record=stage1-evidence/production-contract-implementation.v1.json
stage1_historical_record_sha256=3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31
stage1_historical_review=stage1-evidence/independent-review.v1.md
stage1_historical_review_sha256=10117a7c8c4eec19c33e3ad841c99fb301c43fcda71f8d7addbde4070646f72c
stage1_r2_remediation=stage1-successor-evidence/r2-remediation.v1/stage1-r2-remediation-record.v1.json
stage1_r2_remediation_sha256=97203433ca9dcf7f36e98f4dca2461d60f0159515f002127c153a5e061f74efe
return_contract=08_stage1-stage2-additive-successor-return-contract.v1.md
return_contract_sha256=77db632919118f7a37924634453f38eae260261de78ac4f063743db818325dc5
```

冻结规范仍为 `00`、`01`、`02`、`04`、`05`；其 accepted SHA-256 与 `07` 相同。`06`、`07` 是 mutable projection，不是 candidate authority。v3 candidate/evidence 是 immutable history，不得覆盖或借用为 v4 PASS。

任何上述 input byte、digest、commit、tree、parent、strategy 或 lineage 漂移都会使本合同失效。

## 2. Objective

让 v4 exact candidate 的完整验证成为 candidate-bound evidence；核验远端 required checks 对该 SHA 的不可绕过性；只从 v4 构建可验证、不可覆盖、可回退的 backend、frontend 和 migration artifacts，并产生 SBOM、provenance、漏洞扫描、signature/attestation verification 与 reproducibility evidence。

Stage 3 的完成只建立 release-candidate artifact evidence，不部署这些制品，也不产生 Stage 4 staging authority。

## 3. Preconditions

1. candidate root 存在，HEAD/tree/parent 精确匹配，status 空，非 shallow、无 alternates、Git fsck PASS；
2. manifest、closure、R1/R2/R3、record、materialization receipts 及 Stage 0/1 lineage SHA-256 未漂移；
3. fresh R1、R2 focused/conformance、R3、历史 Stage 1 checker 和 R2 remediation checker 均 PASS；
4. v4 包含 `scripts/formal_release/check_release_evidence.py` 与 `tests/formal_release/test_check_release_evidence.py`；
5. required workflow 仍 fail-closed 依赖 `evidence-validation-check`；
6. 没有 active project writer、Git lock 或另一 Stage 3 worker；
7. 所有可能写入 remote、registry、signing service 或 workflow state 的操作均保持未授权。

前置不满足时，必须先返回 `INPUT_DRIFT`、`REBUILD_REQUIRED` 或精确 blocker，不得进入长 suite/build。

## 4. Allowed reads and writes

### Allowed reads

- v4 candidate 全部 tracked bytes及第 1 节全部 evidence；
- v3 history 的只读 identity/hash；
- 当前本地 build/test toolchain、公开依赖/漏洞数据和只读 Git remote metadata；
- read-only GitHub workflow、run、check、branch-protection/ruleset API；
- read-only artifact registry、transparency/provenance/signature metadata；
- 为归属 warning、skip、failure 和 reproducibility difference 所需的测试、配置与日志。

### Allowed writes

- `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v4/` 内 create-only evidence；
- `/private/tmp/mrw-stage3-v4-*` disposable standalone clones、logs、build contexts 和 outputs；
- Stage 3 唯一命名的 local disposable containers、images、OCI archives 和 caches；
- 本地 unsigned SBOM、provenance statement、scan results 和 verification reports。

本合同不授权任何外部持久写。worker 不得修改本合同、`00`–`09`、v4 canonical candidate、v3 history、主 checkout 产品字节或任何 Stage 0–2 record/evidence。

### Forbidden actions

- 从主 dirty checkout 构建、测试或打包 release artifact；
- 修改 canonical v4 candidate，或运行会产生其 tracked/untracked 状态的命令；
- 修改源码、workflow、Dockerfile/compose、migration、lockfile、版本或 production config；
- reset、clean、stash、rebase、commit、tag、push、force-push、remote branch/ruleset mutation；
- workflow dispatch、registry publish/promotion、创建 signing key、keyless transparency-log write；
- staging/production deploy、生产 secret、live provider、production canonical write、external delivery、canary、cutover、authority transfer、legacy retirement；
- 覆盖同名 artifact/evidence，隐藏 warning/skip/deselect/failure，或把 synthetic R2 fixture、历史 v3 evidence、本地绿色测试冒充远端 required-check PASS。

## 5. Ordered execution

1. 重新核验全部 preconditions，先写 create-only precondition record；
2. 从 v4 创建 disposable standalone clone；不得在 canonical candidate 安装或构建；
3. 对 exact v4 重新运行 R1、R2、R3；
4. 运行 backend、frontend、migration、architecture、law、negative/failure、security 和 Docker/full-stack required gates；
5. 对 PostgreSQL opt-in suites 使用唯一 disposable DB 并清理 residue；
6. 对 remote 只读核验 v4 SHA 是否存在、workflow/check-run head SHA 是否精确、required jobs/ruleset 是否不可绕过；
7. 只从 v4 clean build context 生成 backend/frontend/migration artifacts 与 immutable local digests；
8. 在第二个干净 standalone 环境重建并比较 digest；
9. 生成 SBOM、provenance、scan 和 signature/attestation verification evidence；没有真实签名时标记 `UNEXECUTED` 或 `AWAITING_HUMAN_AUTHORITY`，不得伪造；
10. 核验可用 registry metadata 的 immutability；无可核验的真实 digest/namespace 时保留 blocker；
11. 生成实际 candidate-bound release evidence manifest，并用 v4 内 R2 validator 验证；
12. 清理 task-owned resources，回传结构化结果。

若 remote candidate SHA、registry publish、signing 或 workflow dispatch 缺 authority，不得提前跳过可独立完成的本地验证与制品证据；先完成所有安全、无依赖的本地/read-only 工作，再返回 `AWAITING_HUMAN_AUTHORITY`，同时明确哪些 Stage 3 gate 尚未满足。

## 6. Acceptance checks

`PASS` 必须同时满足：

1. exact v4 fresh R1、R2、R3 全部 PASS；
2. backend unit、integration、core-business、schema/migration、successor-runtime 全量门禁 PASS；
3. architecture、registry、law、exact-byte、negative/failure 门禁 PASS；
4. PostgreSQL opt-in suites PASS 且 teardown residue 为 0；
5. frontend frozen install、lint、typecheck、build、component/e2e PASS；
6. Bandit、`pip-audit`、gitleaks、frontend dependency audit 和 image scan 均有真实结果，blocker 已裁决；
7. Docker build 与 full-stack smoke PASS，production compose 无 source bind mount；
8. GitHub live readback 证明 required workflow/jobs 精确绑定 v4 SHA、required conclusions 全部 success 且不可绕过；
9. 所有 base/compose image digest pinned，无 production `latest`；
10. backend、frontend、migration runner 分别有 immutable digest；
11. 两个独立 clean build 对同一 v4 得到相同 digest；不能 bit-for-bit 时声明差异域，并以签名 provenance 与运行等价门禁支持受限结论；
12. SBOM、build provenance、vulnerability result、signature/attestation verification 全部绑定 artifact digest 与 v4；
13. registry artifact 使用不可变 digest 或不可覆盖 namespace，并有 read-only readback；
14. release manifest 绑定 v4 commit/tree、artifact digests、build/run identity、toolchain/platform 和全部 evidence hashes；
15. 实际 release evidence manifest 使用 v4 R2 validator 验证，synthetic fixture 不计入 ready family；
16. warning、skip、deselect、environment block、native abort、scanner exception 全部逐项归属；
17. disposable resources 清理完成，或 retained evidence 有 exact owner/path/reason/recovery；
18. `external_effects=[]`，authority ceiling 保持不变。

只完成本地测试/构建、只证明 workflow 文本存在、只有 synthetic R2 PASS、缺 remote required-check readback、缺 immutable registry readback或缺真实 signature verification，均不足以 Stage 3 PASS。

## 7. Evidence schema

主记录 schema：`mrw.formal_release.stage3.candidate_artifact.v2`。至少包含：

```text
schema_version
record_id
stage_id=STAGE_3
candidate_generation=V4_ADDITIVE_SUCCESSOR
status
authoritative=false
candidate_commit
candidate_tree
input_refs_and_sha256
toolchain_and_platforms
fresh_r1_r2_r3
test_families_and_exact_results
warning_skip_deselect_inventory
ci_run_id_and_head_sha
required_jobs_and_conclusions
remote_enforcement_readback
artifact_names_and_immutable_digests
reproducibility_class
declared_platform_differences
sbom_refs_and_sha256
provenance_refs_and_sha256
security_scan_results
signature_and_attestation_verification
registry_immutability_readback
release_evidence_manifest_and_r2_result
external_effects
cleanup_and_retained_resources
open_failures
authority_ceiling
observed_at
```

所有 JSON 根类型、schema、ID、status vocabulary、必填字段和 evidence ref/hash 配对必须可确定性验证。每个 `PASS` ref 的路径必须存在且 hash 匹配。secret、token、cookie、private key 和敏感正文不得进入 evidence。

## 8. Stop, retry, rollback

立即停止扩大受影响工作面并回传：

- `INPUT_DRIFT`：candidate/contract/record/evidence identity mismatch；
- `REBUILD_REQUIRED`：修复需要改变 source、workflow、Docker、migration、lockfile、config、version 或 Stage 0–2 binding；
- `FAILED`：required local gate 确定性失败且归属明确；
- `BLOCKED`：环境、toolchain、scanner、remote read-only access 或依赖 blocker；
- `AWAITING_HUMAN_AUTHORITY`：PASS 需要本合同未授权的 push、workflow dispatch、registry/signing 或其他外部持久 effect；
- `AWAITING_OBSERVATION_WINDOW`：真实外部服务存在不可压缩等待期。

同一失败最多尝试两种有实质差异的方案；无新证据即停止。长 suite/build 只允许一次原因明确的同输入重跑。网络瞬时失败可 bounded retry，记录次数和退避。authority 缺失不能通过 retry 解决。

删除或隔离 `/private/tmp/mrw-stage3-v4-*` 和 Stage 3 唯一 cache/container/image；只按精确 ID 清理，不影响既有服务。保留 create-only negative evidence。任何意外 external effect 必须记录 identity、owner、撤销路径与当前状态，worker 不得自动扩大 cleanup。

## 9. Completion signal

worker 必须在自身任务 final answer 中，并通过 `send_message_to_thread` 向 Supervisor task `01a0748b-be3b-7da2-9cb2-4160756bf10b` 回传：

```text
STAGE_RESULT: PASS | INPUT_DRIFT | REBUILD_REQUIRED | FAILED | BLOCKED | AWAITING_HUMAN_AUTHORITY | AWAITING_OBSERVATION_WINDOW
stage_id: STAGE_3
candidate_generation: V4_ADDITIVE_SUCCESSOR
input_commit:
input_tree:
input_refs_and_sha256:
changed_paths:
evidence_paths_and_sha256:
fresh_r1_r2_r3:
test_families_and_exact_results:
warning_skip_deselect_inventory:
ci_run_id_and_head_sha:
required_jobs_and_conclusions:
remote_enforcement_readback:
artifact_names_and_immutable_digests:
reproducibility_result:
sbom_provenance_scan_signature_results:
registry_immutability_readback:
release_evidence_manifest_and_r2_result:
external_effects:
cleanup_and_recovery_status:
residual_blockers:
authority_ceiling:
recommended_next_action:
```

只有 `STAGE_RESULT: PASS` 经 Supervisor 独立验收后，才允许编写 Stage 4 合同。其他状态不得进入 Stage 4；小范围 Stage 3 补证返回原 worker，任何 candidate-byte 修复返回 Stage 1/2 additive successor。

## 10. Authority ceiling

```text
NO_DEPLOY
NO_LIVE
NO_PRODUCTION_WRITE
NO_EXTERNAL_DELIVERY
NO_CANARY
NO_CUTOVER
NO_AUTHORITY_TRANSFER
NO_LEGACY_RETIREMENT
NO_PUSH
NO_REMOTE_MUTATION
NO_REGISTRY_WRITE
NO_SIGNING_WRITE
```
