# MRW Stage 1/2 source and static closure return contract（v1）

- Status: `ACTIVE_RETURN_CONTRACT · NOT_AUTHORITY`
- Date: `2026-09-06`
- Supervisor task: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Return trigger: `STAGE_3_V4_REBUILD_REQUIRED`
- Primary failure: `stage3.v4.missing_mrw_functorial_core_modules`
- Ordered scope: `STAGE_1_SOURCE_AND_STATIC_CLOSURE -> STAGE_2_V5_ADDITIVE_SUCCESSOR`
- Stage 4: `NOT_WRITTEN_NOT_ELIGIBLE`
- Strategy: `REMEDIATION_INCLUSIVE_RELEASE`

本合同修复 v4 的 source-closure 失败，并在再次冻结 candidate 前闭合已确认的 Stage 3 static-input gaps。它不是 Stage 3 或 Stage 4 合同，不授权执行 remote mutation、registry/signing write、deploy、live、production write、external delivery、canary 或 cutover。

## 1. Historical objects and frozen inputs

v4 必须永久保留为 failed Stage 3 history：

```text
historical_candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v4
historical_candidate_commit=e1aa59708a22e4238c4d9beaf7b7bd2d2095d483
historical_candidate_tree=d2003fbb8e54c8dd743fa4e84907a8a978ef5107
historical_manifest_sha256=abc012b5c114d2d280db5bc5fc24c5591caa5bacc76840b154ec848dca5ae8b0
historical_closure_sha256=6e3cf6dfd3ac7c336e81ab5c9b2e310373de7b981edce88109261ac031575c18
historical_r1_sha256=79f7301e0c1e08553982ccc5c88f5854113825c81019ef6244da6bbd025260f0
historical_r2_sha256=8e37eee14ea2eb865a048f57fec7ca55346da642509dc65ac99899b3d69a87ce
historical_r3_sha256=86c67a4532a5a125f65c8f7405bd2b4b775472112e1577d85355fe6001ff5383
historical_record_sha256=e2797d157c0a97f70b382d6ee6197bbcb073f6e55ac6ced5abe6946318345891
historical_stage3_index=stage3-evidence/v4/evidence-index.v2.json
historical_stage3_index_sha256=fbe1914ff111879edd1d1f5db02b7322232bdfa0bf05e752581ce2ea53992926
```

v3 history、`00`–`09`、Stage 0 completion、Stage 1 historical record/review、R2 remediation record 和既有 Stage 2 evidence 均只读。冻结计划 `04` 与 freeze `05` 的 SHA-256 仍为：

```text
stage_plan_04_sha256=d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa
stage_freeze_05_sha256=06d2ec76f7c59973997311ac7ae416005ae0b9c7784598b11127e436dcf8a2aa
```

任何历史 input hash 漂移立即返回 `INPUT_DRIFT`。不得覆盖、修改、删除或复用 v3/v4 candidate/evidence 路径。

## 2. Current source snapshot

```text
source_root=/Users/wangyiliang/market-research-workflow
source_head_at_dispatch=3706655f372f6d34fc62683551b8c3d1f4ff8146
source_tree_at_dispatch=5840bf9ba906c49f70020d226c54446f4ba5aa33
target_1=src/mrw_functorial_kit/core/w07_semantics.py
target_1_status=UNTRACKED_USER_OWNED
target_1_sha256=5afc74cc58d59ea2e788758a542906171f2fe82f4edbd87aa2edba24d6b29fe4
target_2=src/mrw_functorial_kit/core/agent_service_semantics.py
target_2_status=UNTRACKED_USER_OWNED
target_2_sha256=c23c3d7c303614b7d601d0f2cb40046e06b0c8f81814cb91d687219cce3a32dd
workflow=.github/workflows/backend-tests.yml
workflow_status=MODIFIED_USER_OWNED
workflow_sha256=567fdca6904fbf0e5debc037c656e1b9f722f629a6d886a31c1282eba6f6877f
required_checks=.github/branch-protection-required-checks.json
required_checks_status=MODIFIED_USER_OWNED
required_checks_sha256=cb4d61a900a626b71d089717a2210c6cac008ec943bfdac07590f31e618e6355
source_module_focused_at_dispatch=PASS:61_with_2_pydantic_deprecation_warnings
```

主 checkout 有大量用户拥有的并发修改。worker 必须在首次写入前重新采样这些目标的 status/hash，并保护所有无关变化；不得 reset、clean、stash、checkout 覆盖、提交或删除主 checkout。任一目标 byte 漂移时停止写入并回传 exact diff/hash，不得猜测新 owner 意图。

## 3. Phase A — Stage 1 source closure

### Objective

使所有 candidate-local `mrw_functorial_kit.core` imports 可由 candidate 自身解析，不再依赖主 checkout 未跟踪文件；为 source inclusion 建立 deterministic fail-closed checker/test，使后续 Stage 2 在 materialization 前拒绝 required imported module 缺失。

### Required work

1. 审阅两个目标模块、`src/mrw_functorial_kit/core/__init__.py`、7 个 v4 consumers 和其 exact-bound failure vocabularies；
2. 若 dispatch bytes 语义正确，保持不变并纳入 source closure；若需修改，提供逐项语义理由、新 hash 和 focused tests；
3. 运行并扩充 W02/W07 failure-family、P0 registry、backend functorial-debt 和直接 consumer import tests；
4. 新增或扩展 candidate source-closure checker，使 declared package exports、直接 internal imports 和 Stage 1 required source list 在 materialization 前 fail-closed；
5. checker 必须有 positive/negative tests，至少覆盖缺失 `w07_semantics.py`、缺失 `agent_service_semantics.py`、unknown exported name 和 source/manifest omission；
6. 对 workflow-equivalent backend-unit selector完成 collection/execution，collection errors 必须为 0；不得仅运行 61 个 focused tests就宣称 closure complete；
7. warning、skip、deselect 和 collection inventory 必须保留 exact owner与计数。

## 4. Phase B — Stage 1 static Stage 3 readiness closure

Supervisor 已确认 v4 的 required workflow 只含 frontend lint/typecheck/build，没有独立 required frontend component/e2e execution；security job 没有 frontend dependency audit；artifact path 没有 image scan；artifact-metadata 只构建一个 backend image，没有分别绑定 frontend 与 migration runner immutable digests。

worker 必须依据冻结 `04` 的 Stage 3 要求，先做 deterministic static audit，再对确认缺口作最小实现：

1. required CI 中建立 frontend component/e2e execution，且失败进入 required convergence；
2. frontend dependency audit 进入 required security/convergence path，不得 `continue-on-error`；
3. 对实际 release images 建立 image vulnerability scan，并把 blocker 传递到 required convergence；
4. backend、frontend、migration runner 的 artifact identity、build context、Dockerfile/entrypoint 和 immutable digest 必须分别显式；共享同一基础 image 时仍须说明角色 identity 与可观察差异，不能用一个模糊 `mrw-release` digest冒充三个制品；
5. SBOM/provenance/signature/attestation metadata 必须按三个 artifact identity 绑定；本任务只实现并测试 workflow/build contract，不执行外部 signing/registry writes；
6. 更新 branch-protection declaration、required convergence、static production checker 和 fail-closed contract tests，使上述 job/step 缺失、可绕过或只构建单一 artifact 时确定性失败；
7. 生成 create-only Stage 1 source/static remediation record，绑定历史 Stage 1 records、v4 failure evidence、全部 changed paths/hashes、focused receipts、warning inventory 和 authority ceiling；
8. 对该 record 使用 deterministic checker 或 fresh independent review。无 checker 的手写摘要不能作为完成证据。

如果审计证明某项已有等价实现，必须给出 exact job/step/artifact identity、checker witness 和为什么满足冻结要求；不得仅凭名称相似标记 PASS。

## 5. Phase C — Stage 2 v5 additive successor

Phase A/B 全部 PASS 后，使用现有 fail-closed Stage 2 intake/materializer/record 工具生成新的 standalone candidate：

```text
successor_candidate_root=/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v5
successor_evidence_root=/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v5
```

建议路径若已存在，立即返回 `TARGET_ALREADY_EXISTS`，不得覆盖、清理或自选模糊 suffix。v5 必须有新的 commit/tree/manifest/closure/R1/R2/R3/record/primary replay receipts，并显式 supersede v4，不修改 v4。

## 6. Allowed writes and forbidden actions

### Allowed writes

- 两个目标 core module 及其直接 `__init__`/consumer/failure-family tests；
- source-closure checker/test 与 Stage 2 intake/preflight integration；
- required workflow、branch-protection declaration、static production checker/tests；
- 为三个 artifact role 必需的最小 Dockerfile/entrypoint/build metadata/schema/test；
- `stage1-successor-evidence/` 下新的 create-only source/static remediation evidence；
- v5 candidate/evidence create-only roots；
- `/private/tmp/mrw-stage12-v5-*` disposable clones、logs 和 fixtures。

### Forbidden actions

- 修改 v3/v4 candidate/evidence 或 `00`–`10`；
- 改动无关产品/架构/研究内容，或复制整栈平行实现；
- reset、clean、stash、rebase、main checkout commit、tag、push、force-push；
- 用 PYTHONPATH、copy-to-clone、test deselection、skip、baseline 或 relaxed import替代 source inclusion；
- 把 component test、frontend audit 或 image scan设为 non-blocking；
- 从主 dirty checkout 构建 release artifact 或宣称 exact candidate；
- workflow dispatch、remote mutation、registry publish/promotion、signing/key creation；
- staging/production deploy、live provider、production canonical write、external delivery、canary、cutover、authority transfer、legacy retirement。

## 7. Acceptance

### Stage 1 source/static acceptance

1. 两个 core modules 在目标 bytes 未漂移的前提下被 lawful inclusion，candidate-independent focused tests PASS；
2. 7 个已知 consumers 及 closed package exports全部可解析；
3. source-closure checker positive/negative suite PASS，并接入 candidate intake/precondition；
4. 61-test baseline至少保持 PASS，新增 tests 有明确计数；
5. workflow-equivalent backend-unit selector exit 0，collection errors=0；skip/deselect均归属；
6. frontend component/e2e required path、frontend dependency audit、image scan和三 artifact identities 静态 closure PASS；
7. workflow/branch-protection/required-convergence/static checker fail-closed tests PASS；
8. Python lint/compile 与相关 frontend config/type validation PASS；
9. create-only Stage 1 remediation record及其 checker/review PASS；
10. 不修改历史对象，无 external effects。

### Stage 2 v5 acceptance

1. v5 roots 在写入前不存在，v3/v4 始终 exact/clean；
2. manifest 包含所有新增 source/checker/test/workflow/artifact-contract/evidence bytes；
3. manifest path set 与 candidate raw delta精确相等；
4. v5 HEAD/tree/parent 与 record 一致，tracked/untracked=0，Git fsck PASS；
5. v5 非 shallow、无 alternates、无 shared object inode；
6. fresh R1、R2 conformance、R3、Stage 1 historical/R2/source-static remediation checkers全部 PASS；
7. source-closure checker和 workflow-equivalent backend-unit gate从 v5 自身 PASS；
8. primary/replay得到相同 commit/tree；
9. manifest、closure、R1/R2/R3、record、materialization receipts 均 create-only 且 hash/ref 配对；
10. candidate/evidence 不含 secret、cache、DB、日志、临时输出或 mutable progress；
11. task resources清理完成，无 external effects；
12. authority ceiling保持不变。

v5 PASS 只恢复重新派发 Stage 3 的资格；不等于 Stage 3 PASS或 production release。

## 8. Stop and result vocabulary

- `INPUT_DRIFT`：frozen/history/dispatch target bytes漂移；
- `TARGET_ALREADY_EXISTS`：v5 target root已存在；
- `STAGE_1_SOURCE_CLOSURE_FAILED`：module/import/checker/backend-unit collection失败；
- `STAGE_1_STATIC_CLOSURE_FAILED`：workflow/security/artifact static contract失败；
- `STAGE_2_REBUILD_FAILED`：intake/materializer/replay/R1/R2/R3/record失败；
- `REBUILD_REQUIRED_AGAIN`：出现新且未闭合的 candidate-byte dependency；
- `BLOCKED`：精确环境/toolchain/资源 blocker；
- `AWAITING_HUMAN_AUTHORITY`：需要未授权外部持久 effect。

同一失败最多两种实质不同方案。不得通过隐藏 warning/skip、缩小 required test selector 或引用历史 PASS 变更状态。

## 9. Completion signal

worker 必须在自身任务 final answer 中，并通过 `send_message_to_thread` 向 Supervisor task `01a0748b-be3b-7da2-9cb2-4160756bf10b` 回传：

```text
RETURN_RESULT: PASS | INPUT_DRIFT | TARGET_ALREADY_EXISTS | STAGE_1_SOURCE_CLOSURE_FAILED | STAGE_1_STATIC_CLOSURE_FAILED | STAGE_2_REBUILD_FAILED | REBUILD_REQUIRED_AGAIN | BLOCKED | AWAITING_HUMAN_AUTHORITY
return_scope: STAGE_1_SOURCE_AND_STATIC_CLOSURE_AND_STAGE_2_V5_SUCCESSOR
input_source_identity_and_hashes:
changed_paths:
source_closure_checker_and_results:
backend_unit_gate_result:
static_stage3_readiness_results:
stage1_remediation_record_and_sha256:
stage1_focused_tests_lint_compile:
successor_candidate_root:
successor_commit:
successor_tree:
successor_manifest_path_and_sha256:
successor_closure_path_and_sha256:
successor_r1_r2_r3_paths_and_sha256:
successor_record_path_and_sha256:
primary_replay_receipts_and_sha256:
v5_fresh_checks:
historical_v3_v4_unchanged:
warning_skip_deselect_inventory:
external_effects:
cleanup_and_recovery_status:
residual_blockers:
authority_ceiling:
recommended_next_action:
```

只有 `RETURN_RESULT: PASS` 经 Supervisor 独立验收后，才允许编写绑定 v5 的新 Stage 3 合同。不得直接进入 Stage 4。

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
