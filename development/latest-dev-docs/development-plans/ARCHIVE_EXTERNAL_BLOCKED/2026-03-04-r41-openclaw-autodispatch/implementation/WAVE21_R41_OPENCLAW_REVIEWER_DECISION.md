# WAVE21 R41 OpenClaw Reviewer Decision

Date: 2026-05-22
Topic: 2026-03-04-r41-openclaw-autodispatch

## Decision
- Result: `external_blocked`
- Internal status: No internal repo blocker detected
- Reason: Mirror/runtime handoff/readback are self-consistent in-repo, but external OpenClaw runtime verification is explicitly not executed.

## Evidence
1. Mirror manifest
- `implementation/WAVE20_R41_OPENCLAW_MIRROR_READBACK_EVIDENCE.md` records:
  - `local_mirror_status: local_mirror_passed`
  - `external_runtime_status: external_runtime_unverified`
  - `missing_artifact: missing_artifact`
  - `closure_claim_allowed: false`
- Evidence claim requires deterministic manifest readback and labels external runtime as unverified.

2. Runtime handoff
- `implementation/WAVE15_R41_OPENCLAW_RUNTIME_HANDOFF_EVIDENCE.md` records:
  - `runtime_handoff_status: repo_local_handoff_mirror_only`
  - `external_openclaw_runtime_live_verified: false`
  - `external_runtime_checked: false`
  - SA1/SA2/SA3 notes all indicate `ready_dispatch_count=0` and skipped A-F autodispatch lines.

3. Reference pool
- `R41_INTERFACE_CONTRACT.md` binds required fields for lines A-F and references:
  - `reference-pool/2026-03-04-scout-r41/AB-envelope.md`
  - `reference-pool/2026-03-04-scout-r41/CD-envelope.md`
  - `reference-pool/2026-03-04-scout-r41/EF-envelope.md`
  - `reference-pool/2026-03-04-scout-r41/codex_handoff.md`
- `reference-pool/2026-03-04-scout-r41/codex_handoff.md` includes must_to_atomic handoff tasks and seed/fingerprint/closure-related requirements; `reference-pool/.../INDEX.md` confirms the full batch includes 11 artifacts.

4. Local validation run (completed by reviewer)
- `python3 scripts/checkers/check_r41_openclaw_autodispatch_gate.py`
- `python3 scripts/checkers/check_r41_openclaw_runtime_handoff.py`
- `python3 scripts/checkers/check_r41_openclaw_mirror_runtime_manifest_readback.py`
- `python3 -m unittest tests.checkers.test_check_r41_openclaw_autodispatch_gate_unittest tests.checkers.test_check_r41_openclaw_runtime_handoff_unittest tests.checkers.test_check_r41_openclaw_mirror_runtime_manifest_readback_unittest`
- All pass, with outputs consistent with the above flags (`external_runtime_checked=false`, `external_openclaw_runtime_live_verified=false`, `external_runtime_status=external_runtime_unverified`).

## Risk
- 主要风险是 `external_blocked`：当前不能确认外部 OpenClaw `autodispatch` 与 runtime handoff 的真实闭环。
- Mirror 和 handoff 的一致性仅是 repo-local；迁档后若未先完成外部核验，可能出现 runtime 侧签核缺口。
- A-F 目前为 no-op/autodispatch skipped，迁档后若外部运行态引擎启用，需确保不带入该 topic 的非空任务。

## Recommended migration actions
- 暂停对 R41 的外部迁档闭环宣告；保留 `external_blocked`。
- 在外部 `/Users/wangyiliang/Desktop/openclaw` 环境完成以下动作后，再解除 `external_blocked`：
  1. 运行 OpenClaw autodispatch 与 runtime handoff/live 检查（需覆盖外部 runtime 读出）。
  2. 确认外部 run state 中不再返回待处理 line task，且可形成可追溯 `seed/runtime_fingerprint`。
  3. 在外部完成的前提下补齐 reviewer 证据中的 external-runtime status/verified 字段。
  4. 复测上述三个 checker 与对应 unit test，并更新 `WAVE20` 与 `WAVE15` 证据中的外部边界字段。
