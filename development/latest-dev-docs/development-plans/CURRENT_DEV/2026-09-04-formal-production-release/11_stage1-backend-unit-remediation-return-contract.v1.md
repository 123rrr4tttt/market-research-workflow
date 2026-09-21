# Stage 1 backend-unit remediation return contract v1

- Date: 2026-09-06
- Status: `ACTIVE_RETURN_CONTRACT_NOT_AUTHORITY`
- Supervisor: `01a0748b-be3b-7da2-9cb2-4160756bf10b`
- Executor, reused: `01a074e1-da0d-7a70-9c45-daff7b8bc9ad`
- Parent contract: `10_stage1-stage2-source-and-static-closure-return-contract.v1.md`
- Parent SHA-256: `0c20328727fdefca6a3161e212490a2043efeee17e4bffc854f8ee17847cdd6b`
- Trigger: `RETURN_RESULT: STAGE_1_SOURCE_CLOSURE_FAILED`

本合同追加 Phase A 的 backend-unit 修复范围，历史合同保持原样。完成本合同的修复后，从合同 10 Phase A 重新验证，依次执行 B、C；只有 A/B 全部 PASS 才建立 v5。Stage 3 等待 v5 独立验收，Stage 4 尚未准入。

## 1. Supervisor acceptance of the failed return

失败回传成立，不构成 Stage 1 验收通过。Supervisor 重算了四个 changed-path hashes、两个 core module hashes、workflow/check declaration hashes 及三个诊断日志 hashes，均与回传匹配。

- Source-closure + intake focused rerun: `96 passed`；direct source checker `PASS`；Homebrew ruff 和 compileall `PASS`。backend venv 没有 ruff module，随后使用已安装的 `/opt/homebrew/bin/ruff`。
- Worker complete-selector attempt: exit 134；原始日志 `7860894a583ee97f0a0f4468feb3d82f9edb262a27d5437364d560984020be6b`，路径 `/private/tmp/mrw-stage1-backend-unit.workflow-equivalent-final.log`。回传的 progress-marker counts 不是 terminal totals，必须从原始日志重新计数并纠正差异。
- Supervisor `-x -vv` diagnostic: `1 failed, 192 passed, 2328 deselected, 13 warnings, 2 subtests passed`；4094 collected / 1766 selected；首次失败为 `tests/successor_runtime/test_i1_micro_specimens.py::test_i1_additive_binding_candidate_is_live_history_green_and_read_only`。
- 首次失败原文：`FAIL family_fragment_rebind: live logical path mismatch: scripts/generate_stage0_i1_exact_binding_rebind.py`。B22 source reference hash 为 `badde41245712a95f6f0994c910fedf39eef75a972e45033ae102b9cb8a1288e`；当前脚本和 v4 脚本均为 `a49d65e98bb6a861168fe3880bec419a010bcb5c7bf18bed911bb45feea92227`。这只是漂移定位，尚未判定应该更换哪个 current reference。
- Supervisor contracts/successor diagnostic shard: `1 failed, 649 passed, 1558 deselected, 13 warnings, 2 subtests passed`。
- Supervisor `tests/unit` diagnostic excluding `test_resource_pool_unified_search_unittest.py`: `66 failed, 1003 passed, 4 skipped, 193 deselected, 4 warnings, 40 subtests passed`。它与 worker abort attempt 的选择、顺序和覆盖不同，禁止拼接成完整 gate receipt。
- 单独 functorial shard 因 test helper import `successor_runtime` 失败；另一诊断命令引用了不存在的 `tests/production_governance` 等目录并 exit 4。这些是诊断限制，不自动计为产品缺陷。

## 2. Ordered remediation

### A1. Isolate the observed external effect before another full run

阅读并最小修复 `main/backend/tests/unit/test_resource_pool_unified_search_unittest.py` 的 effect fixtures。已知触发点 `test_unified_search_forwards_parser_profile_to_search_template` 仅 mock `execute_search_template`；空候选进入 `unified_search.execute_external_site_search`，继而 `search.web.search_sources` / DDGS construction。

在真正的测试 effect boundary mock fallback，并验证 parser-profile forwarding 与 fallback 分支各自应观察的行为。补充回归证明 unit 路径不会调用真实 provider。不得为了测试通过更改 production fallback 默认语义。先 focused 验证，再执行完整 selector。审查同文件与相同 fixture 的相邻分支，避免首次崩溃掩盖后续泄漏。

### A2. Produce a complete failure inventory

沿用 required marker selector `unit and not external and not flaky`；从 workflow、pytest config 和依赖安装方式推导可重放环境，记录所有环境差异。现有本地诊断设置四个 DB/store flags 为 false 并使用 repo-local src PYTHONPATH；这些差异必须说明且在 CI/test setup 合法闭合后才能称 workflow-equivalent。不得依赖主 checkout 的路径来修补候选导入。

安全隔离后生成完整终态日志、JUnit 或等价逐 nodeid receipt。每项失败记录 nodeid、cause、代码/fixture/evidence owner、当前 path/hash、最小修复路径与验证。保留 collect、selected、deselected、skip reason、warnings、subtests、exit code。共享旧 pytest lastfailed cache 不是本轮清单。

### A3. Repair by proven cause

允许修复这份清单证明相关的 backend tests、test fixtures、pytest/import setup，以及直接失败的 backend implementation/caller 和对应 focused tests；每个文件首次写入前记录现有 bytes/status，保护并发用户修改。

1. 旧 evidence 路径：先发现并验证当前 canonical relocation，包括实际内容、身份及摘要绑定。只更新有证据的消费者路径或共享路径解析；禁止复制整份历史、恢复用户删除文件、制造 receipt 或把缺失改成 skip/PASS。需要用户已删除内容而无合法现存来源时记录 `EVIDENCE_SOURCE_UNAVAILABLE`。
2. I1 等 exact-byte binding：先只读核对 B22/B23 lineage、当前 completion references 和 checker 的 live/history 语义。有既存合法 successor 时，消费者可依据其明确 supersession 关系引用；历史验证继续验证冻结字节。禁止无依据给失败检查加 `--history-only`、替换预期 hash、覆盖历史 candidate，或回滚当前脚本以凑旧 hash。需要新的 additive rebind 时先返回 exact affected binding/path/hash 和拟变更内容；本合同不授权改写历史记录或发明新资格。
3. 实际行为回归：依据已有契约修复直接 owner，例如 request defaults、structured result、failure lift context；不得放宽失败族、修改 expected value 隐藏回归或修改无关生产语义。若涉及冻结绑定的 runtime bytes，先识别并遵守 rebind 边界。
4. store/import 问题：unit 测试使用明确 fixture；不得降低生产 fail-closed 配置或接入现有业务数据库。候选使用自身 source 与声明的依赖安装，不使用主 checkout 环境兜底。

对多工作面可分派互斥子代理；主执行任务拥有清单、共享 fixtures、整合及最终 receipt。不得因某个历史绑定待裁决而中止其他无依赖的已授权修复；但 Phase A 通过及 Phase B/C 仍受有序门禁约束。

## 3. Source gate review and acceptance

保留已通过的 source-closure 实现，并验证 intake 对有效 MRW candidate 的真实 projected file set 执行 gate。检查 package 缺失不能经 optional probe 静默绕过，DELETE/遗漏/错误 base overlay 不能由主 checkout 文件掩盖；generic fixture 的可选 probe 不得成为 MRW intake 的逃逸条件。有缺口则在现有实现上最小补全并加 negative tests。

修复验收必须包含：changed paths/hash 与因果清单；对应 focused tests/lint/type checks；完整 required selector exit 0、collection errors 0；skip/deselect/warnings 全量归属；no-live-effect 回归见证；相关 source/intake tests。诊断分片、`-x`、排除 crash 文件的命令均不能替代完整 gate。

通过后继续合同 10 Phase B 的 frontend component/e2e required path、frontend audit、image scan 与三 artifact identities 静态闭合，再生成 Stage 1 remediation record，最后才按 Phase C 建立 v5。既定 v5 roots 已存在则 `TARGET_ALREADY_EXISTS`，不得覆盖或自选 successor suffix。

## 4. Evidence and boundaries

所有 v3/v4 candidate/evidence、合同 00–11、历史 Stage 0/1 records 和 exact-byte snapshots 只读。新增证据可放于 `stage1-successor-evidence/backend-unit-return-v1/`，create-only，记录原始失败与修复后 receipts；临时日志使用唯一 `/private/tmp/mrw-stage12-v5-*` 路径。禁止主 checkout commit/reset/clean/stash、广泛清理、远端执行、registry/signing writes。

authority_ceiling: `NO_DEPLOY_NO_LIVE_NO_PRODUCTION_WRITE_NO_EXTERNAL_DELIVERY_NO_CANARY_NO_CUTOVER_NO_AUTHORITY_TRANSFER_NO_LEGACY_RETIREMENT_NO_PUSH_NO_REMOTE_MUTATION_NO_REGISTRY_WRITE_NO_SIGNING_WRITE`

## 5. Return and task reuse

按合同 10 的 `RETURN_RESULT` schema 回传，加 `backend_failure_inventory`、`effect_isolation_receipt`、`history_binding_disposition`、`workflow_environment_equivalence` 和 `source_gate_negative_receipts` 字段。无法通过时仅列当前真实 blockers，并保留已完成工作证据。结果在本任务 final 与 Supervisor 消息中都发送。

同一 Stage 的返工和补证继续复用本执行任务。Stage 3 后续复用 `01a074c0-5786-7121-8a0b-ffef1e32a2a9`；本任务不创建 Stage 3/4 新任务。

收到 `NEW_TASK:` 或 `NEW_MILESTONE_TASK:` 必须读取并执行，即使旧 goal 已完成；只有 `ACCEPTANCE_FINAL:` 才表示当前阶段可以 idle。
