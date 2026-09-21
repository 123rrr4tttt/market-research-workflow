# MRW Stage 1/2 additive successor return contract（v1）

- Status: `ACTIVE_RETURN_CONTRACT · NOT_AUTHORITY`
- Date: `2026-09-06`
- Supervisor task: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Return trigger: `STAGE_3_REBUILD_REQUIRED`
- Failure ID: `stage3.required_r2_bytes_absent`
- Ordered scope: `STAGE_1_TARGETED_REPAIR -> STAGE_2_ADDITIVE_SUCCESSOR`
- Forbidden next stage: `STAGE_4_NOT_ELIGIBLE`
- Strategy: `REMEDIATION_INCLUSIVE_RELEASE`

本合同只处理 Stage 3 已确定的 R2 required-input 缺陷，并形成 additive Stage 2 successor candidate。它不是 Stage 4 合同，不授权继续 Stage 3 全量制品工作，也不产生 deployment、live provider、production canonical write、external delivery、canary、cutover、authority transfer、legacy retirement、push、remote mutation、registry write 或 signing write 权限。

## 1. 因果边界与历史保留

Stage 2 v3 已按当时合同完成 exact candidate freeze；Stage 3 随后的 required-input 检查发现该 candidate 缺少 CI 所调用的 R2 checker/test。两件事同时成立：

1. v3 的历史完成记录和 exact identity 不被改写；
2. v3 不能继续作为 Stage 3 可验收输入，必须由 additive successor 取代。

必须保持不变的历史对象：

```text
historical_candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v3
historical_candidate_commit=f8d84afc2784cf91784da957e353e2b0c0d6952c
historical_candidate_tree=1be3dcbc009332ec225297d1b94430862287d816
historical_manifest=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/candidate-manifest.v3.json
historical_manifest_sha256=a95e4103dfa3743c6a603079f838d48a20665b38afe7fa2a9b2623ab443522bf
historical_closure=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/closure.final.v3.json
historical_closure_sha256=53497a752a9207b4dc54f8a5ab7e8af23d3f937a82fb71c8e8bc3092fc410808
historical_r1=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/r1.final.v3.json
historical_r1_sha256=fdd6053faeada17b62c050207078ff5944a3c759eb5d6183a43ac4f74cc4774e
historical_record=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v3/stage2-record.final.v3.json
historical_record_sha256=46d0df3f320619508130f87f6f8d60baba6c6080918293f3d021fbe7e26fb312
```

不得覆盖、修改、删除、重命名或复用这些路径。

## 2. 冻结输入

### 2.1 规范与验收记录

```text
formal_release_plan_00_sha256=97801ddbe46233429309f218cfcb183ade785ffd1a2d0872223907851ca95087
formal_release_gap_01_sha256=21df93d7c9dc1ac3cc77a9a449f3c37527001f0716551ce34db032c7c93754a0
formal_release_freeze_02_sha256=65e5b4a759d5ea2c815541bd8c4a864ab4130fccbe39d50214787edff5082c2a
formal_release_progress_03_sha256=0191e27c0c7ff28ba0c0cd5c8b5985be3cad3711a794f4fd70d9d76ed08e1d4c
production_stage_plan_04_sha256=d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa
production_stage_freeze_05_sha256=06d2ec76f7c59973997311ac7ae416005ae0b9c7784598b11127e436dcf8a2aa
stage0_completion_sha256=4911df1c6450d9802ac7bd6b0669ef3a7343e3ce308d33f0a46dde2c4cb62dda
stage1_historical_record_sha256=3f5c745ce8253522fa7e3728ba112ed41c80f3b6aa7409ddf028621c6ae07f31
stage1_historical_review_sha256=10117a7c8c4eec19c33e3ad841c99fb301c43fcda71f8d7addbde4070646f72c
stage3_preconditions_sha256=4f63e5cf764d7aad4fcb3f18f422a7fa2d4195ac8066b1d19196137d0cffcf2a
stage3_candidate_artifact_sha256=f2075bf4742ea711be6402204be5c54d54f8f8b5446eab952c2d2f34d1b5965e
```

`06` 和 `07` 是 mutable、derived、non-authority 的进度投影；worker 不得修改。其内容可用于定位历史 identity，但不能反向改变冻结规范。

### 2.2 当前修复输入快照

```text
source_root=/Users/wangyiliang/market-research-workflow
source_head_at_dispatch=3706655f372f6d34fc62683551b8c3d1f4ff8146
source_tree_at_dispatch=5840bf9ba906c49f70020d226c54446f4ba5aa33
r2_checker=scripts/formal_release/check_release_evidence.py
r2_checker_status_at_dispatch=UNTRACKED_USER_OWNED
r2_checker_sha256_at_dispatch=cecb9a08b6ef23c1ee25d5e6955f35e2539ceead3e5e2568076482aa6dd34c35
r2_test=tests/formal_release/test_check_release_evidence.py
r2_test_status_at_dispatch=UNTRACKED_USER_OWNED
r2_test_sha256_at_dispatch=fe1e58cb6ee2d5eaba60325a510297a98b87a730325376c55b5cc8c58c1faa95
r2_focused_at_dispatch=PASS:9
```

主 checkout 含大量用户拥有的脏状态。worker 必须重新采样并记录 source identity/status，保护并发变化；不得 reset、clean、stash、checkout 覆盖、删除或提交主 checkout。若两个目标文件在执行前漂移，先停止写入并回传精确 diff/hash/owner，不得静默采用未知新字节。

## 3. Ordered objective

### Phase A：Stage 1 targeted repair

把两个 R2 路径纳入正式 release input closure，使 required workflow 的 `evidence-validation-check` 不再引用 candidate 中不存在的文件；同时为 Stage 1 历史记录增加 create-only successor/remediation evidence，不覆盖既有 v1 record 或 review。

只允许修复下列 failure family：

```text
stage3.required_r2_bytes_absent
```

如果完成绑定需要最小调整 Stage 1 generator/checker/test 或 Stage 2 closure/intake 规则，可以修改这些直接依赖面，但必须逐项说明为什么不可省略。不得借此处理无关产品、架构、功能或格式清理。

### Phase B：Stage 2 additive successor

在 Phase A focused acceptance 通过后，使用现有 fail-closed Stage 2 intake/materializer/record 工具，从重新采样的主 checkout 形成新的 standalone exact candidate。successor 必须有新的 root、commit、tree、manifest、closure、R1 和 record；不得就地修补 v3。

建议 create-only 目标：

```text
successor_candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v4
successor_evidence_root=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v4
```

如果建议路径已存在，必须停止并返回 `TARGET_ALREADY_EXISTS`；不得覆盖或自动改用模糊名称。Supervisor 决定新的 additive suffix。

## 4. 允许的读写面

### Allowed reads

- 主 checkout 全部状态、Stage 0/1/2/3 records 与 frozen inputs；
- v3 candidate/evidence 的只读内容和 Git object identity；
- Stage 2 intake、Git batch、materializer、record、R1/R2/R3 checker 及其 tests；
- required workflow、branch-protection declaration 和 release manifest/closure inputs；
- 为最小修复归属所需的 Git status/diff/hash 与 focused test output。

### Allowed writes

- 两个目标 R2 文件，仅在 dispatch hash 未漂移且确有 focused defect 时做最小修改；若无需修改，保持其 exact bytes；
- 与 R2 required binding 直接相关的最小 Stage 1 generator/checker/test、Stage 2 intake/closure/record 工具修改；
- `stage1-evidence/` 或新的 `stage1-successor-evidence/` 下 create-only remediation record/review；
- 建议的 v4 candidate/evidence create-only roots；
- `/private/tmp/mrw-stage12-successor-*` 临时文件、standalone replay clone 和 logs。

所有 repo 内写入都必须 additive 或最小定点修复，不得覆盖历史 evidence。外部 candidate/evidence root 必须在创建前证明不存在。

### Forbidden actions

- 修改或污染 v3 candidate/evidence；
- reset、clean、stash、rebase、主 checkout commit、tag、push、force-push；
- 删除或覆盖用户拥有的无关 modified/untracked 文件；
- 从主 dirty checkout 直接宣称 exact candidate、R1 或 Stage 3 PASS；
- 跳过 Stage 1 binding，直接把两个文件复制到 v3；
- 修改 required workflow 以移除、弱化、continue-on-error 或绕过 R2 job；
- remote branch/ruleset mutation、workflow dispatch、registry publish/promotion、signing/key creation；
- staging/production deploy、live provider、production canonical write、external delivery、canary、cutover、authority transfer 或 legacy retirement。

## 5. Focused acceptance

### 5.1 Phase A acceptance

1. dispatch 时两个目标文件 hash 未漂移，或任何经授权的改动都有 exact diff、理由和新 hash；
2. `tests/formal_release/test_check_release_evidence.py` 全部 PASS；
3. R2 direct CLI help 与至少一个 PASS、一个 fail-closed manifest fixture 验证通过；
4. workflow `evidence-validation-check` 仍调用该 test，且 `artifact-metadata-check`、`required-convergence-check` 的依赖保持 fail-closed；
5. branch-protection declaration 继续要求 `evidence-validation-check`；
6. 新的 Stage 1 remediation record create-only 绑定：历史 Stage 1 record/review、两个 R2 文件、workflow、branch-protection declaration、测试收据、authority ceiling；
7. 对该 remediation record 运行 deterministic checker 或独立 fresh review；任何手写 JSON 都必须有 schema/checker/test，不接受无验证摘要；
8. focused lint/compile 对改动 Python 面通过；warning/skip/deselect 明确归属。

### 5.2 Phase B acceptance

1. successor root 和 evidence root 在写入前不存在，v3 全程保持 exact/clean；
2. successor manifest 显式包含两个 R2 路径以及所有 Stage 0/1 required inputs；
3. manifest path 集合与 candidate 对 base 的 raw delta 精确相等；
4. successor candidate 的 HEAD/tree 与 record 精确一致，tracked/untracked 均为 0；
5. fresh R1 PASS；
6. fresh R2 必须从 successor candidate 自身执行并 PASS，不得引用主 checkout；
7. fresh R3 PASS；
8. historical Stage 1 checker 与新的 remediation checker/review 均对 successor bytes PASS；
9. 两个独立 standalone materialization/replay 得到同一 commit/tree；
10. no shallow、no alternates、no shared object inode，Git fsck PASS；
11. manifest、closure、R1、record 和 remediation evidence 均有 create-only path、SHA-256、schema、status 与 pairwise refs；
12. candidate/evidence 未包含 secret、cache、DB、日志、临时输出或 mutable progress；
13. 所有 task-owned temporary process/file 清理完成，或 retained resource 有 exact owner/reason/recovery；
14. 无 external effects，authority ceiling 保持不变。

successor candidate 建立后也不等于 Stage 3 PASS，更不等于 production release。它只恢复重新派发 Stage 3 的资格。

## 6. Stop and failure rules

立即停止并回传下列任一状态：

- `INPUT_DRIFT`：dispatch hash、frozen hash、historical evidence 或目标文件身份漂移；
- `TARGET_ALREADY_EXISTS`：建议 v4 root 已存在；
- `STAGE_1_REMEDIATION_FAILED`：R2、CI DAG、binding record/checker 或 focused gate 失败；
- `STAGE_2_REBUILD_FAILED`：intake/materializer/replay/R1/R2/R3/record 失败；
- `REBUILD_REQUIRED_AGAIN`：发现新的源码/workflow/config/lockfile/migration 修复面；
- `BLOCKED`：工具链、权限或环境 blocker 有精确 owner；
- `AWAITING_HUMAN_AUTHORITY`：任务需要本合同未授权的外部持久 effect。

同一失败最多尝试两种有实质差异的方案。不得用 skip、baseline、降级 required job、历史 PASS、主 checkout 测试结果或 copy-in-place 将失败改写为 PASS。

## 7. Output schema and completion signal

Stage 1 remediation 主记录至少包含：

```text
schema_version
record_id
status
authoritative=false
failure_id
historical_stage1_record_ref_and_sha256
historical_stage1_review_ref_and_sha256
required_file_refs_and_sha256
workflow_refs_and_sha256
focused_commands_and_exact_results
warning_skip_deselect_inventory
independent_review_or_checker
external_effects
cleanup
authority_ceiling
observed_at
```

worker 必须在自身任务 final answer 中，并通过 `send_message_to_thread` 向 Supervisor task `01a0748b-be3b-7da2-9cb2-4160756bf10b` 回传：

```text
RETURN_RESULT: PASS | INPUT_DRIFT | TARGET_ALREADY_EXISTS | STAGE_1_REMEDIATION_FAILED | STAGE_2_REBUILD_FAILED | REBUILD_REQUIRED_AGAIN | BLOCKED | AWAITING_HUMAN_AUTHORITY
return_scope: STAGE_1_TARGETED_REPAIR_AND_STAGE_2_ADDITIVE_SUCCESSOR
input_source_head:
input_source_tree:
input_target_hashes:
changed_paths:
stage1_remediation_record_and_sha256:
stage1_focused_results:
successor_candidate_root:
successor_commit:
successor_tree:
successor_manifest_path_and_sha256:
successor_closure_path_and_sha256:
successor_r1_path_and_sha256:
successor_record_path_and_sha256:
successor_fresh_r1_r2_r3:
replay_and_object_store_results:
historical_v3_unchanged_check:
warning_skip_deselect_inventory:
external_effects:
cleanup_and_recovery_status:
residual_blockers:
authority_ceiling:
recommended_next_action:
```

只有 `RETURN_RESULT: PASS` 经 Supervisor 独立验收后，才可重新编写并派发 Stage 3 successor 合同。不得直接编写 Stage 4。

## 8. Authority ceiling

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
