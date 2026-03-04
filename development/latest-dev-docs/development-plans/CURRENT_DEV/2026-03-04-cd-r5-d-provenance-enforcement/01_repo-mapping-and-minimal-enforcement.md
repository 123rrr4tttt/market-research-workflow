# C/D线路 R5 - D仓签名与 Provenance 强制校验最小落地（2026-03-04）

## 0) 参考包消费说明

- 本次优先路径 `docs/reference-pool` 不存在，已按约束切换为替代参考包：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-cd-r3-d-security-minimal/01_repo-mapping-and-minimal-implementation.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-rag-line-round3-filter-robustness/01_rag-filter-robustness-minimal-enhancement-2026-03-04.md`
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-d-line-rag-filter-robustness/01_task_and_closing.md`

## 1) Repo-level 映射（R5 执行前）

现状：
- CI 已具备 `security-baseline-check`、`sast-check`、`dast-check`。
- 已有 `scripts/security/verify_provenance_placeholder.sh`，但语义偏占位。
- 存在侧车检查基础（`.sig` / `.intoto.jsonl`），但未强约束 digest 与 release 目录空目录误通过。

缺口：
- release artifact 出现后，仍缺少“强阻断”校验语义（digest 一致性、sidecar 非空、最小 provenance 结构检查）。
- CI job 名称仍为 placeholder 语义，不利于审计口径。

目标（R5 最小原子化）：
- 在不引入外部签名基础设施的前提下，将校验升级到“目录存在即阻断”的最小强约束。
- 保持可回滚（单脚本 + 单 workflow job 命名更新）。

## 2) 最小可回滚改动

改动文件：
- `.github/workflows/backend-tests.yml`
- `scripts/security/verify_provenance_placeholder.sh`

实施内容：
- workflow job 从 `provenance-signature-placeholder-check` 更名为 `provenance-signature-enforcement-check`。
- 脚本升级为 R5 强制策略（在 `artifacts/release` 存在时）：
  - 对每个主 artifact 强制要求 `.sig`、`.intoto.jsonl`、`.sha256` 三类 sidecar。
  - sidecar 必须非空。
  - `.sha256` 必须为 64 位十六进制并与实文件 digest 一致。
  - `.intoto.jsonl` 至少包含 `_type` 或 `subject` 关键字段提示。
  - release 目录存在但无主 artifact 时直接失败，避免“空目录绕过”。
- 当 release 目录不存在时，继续 `exit 0`（不影响未接入发布流的分支）。

## 3) 验证命令与结果

执行命令：

```bash
python3 - <<'PY'
import yaml
with open('.github/workflows/backend-tests.yml','r',encoding='utf-8') as f:
    yaml.safe_load(f)
print('workflow yaml: ok')
PY

bash -n scripts/security/verify_provenance_placeholder.sh
bash scripts/security/verify_provenance_placeholder.sh artifacts/release
```

结果：
- `workflow yaml: ok`
- `bash -n` 通过
- 无 release 目录时输出 `skip enforcement` 并退出 0（符合“未接入发布流不阻断”）

补充正反用例（本地临时目录）：
- 反例：缺 sidecar 时脚本失败退出（`exit 1`）；
- 正例：补齐 `.sig/.intoto.jsonl/.sha256` 后通过。

## 4) 回滚点

未提交场景：

```bash
git checkout -- .github/workflows/backend-tests.yml scripts/security/verify_provenance_placeholder.sh
rm -rf development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-cd-r5-d-provenance-enforcement
```

已提交场景：
- 回滚到本批次 commit hash。

## 5) 风险与边界

- 仍未接入真实密钥体系（如 cosign keyless/KMS），当前为“结构与完整性”阻断，不是“身份信任链”终态。
- `.intoto.jsonl` 当前只做最小字段检查，未做 statement schema 全量校验。
- digest sidecar 格式按“首列 hash”读取，若后续统一为多列格式需同步标准化。

## 6) next-batch-trigger（R6 建议）

1. 当发布流水线开始产出 `artifacts/release/*` 且具备 OIDC/Cosign 条件时，触发 R6：接入 `cosign verify-blob` 与证书身份策略（issuer/subject 约束）。
2. 当 release sidecar 规范稳定后，触发 R6：引入 in-toto statement schema 校验（predicateType/subject digest 对齐）。
3. 当多仓共享发布能力时，触发 R6：将本脚本抽象为复用 action 或可版本化安全脚本包。
