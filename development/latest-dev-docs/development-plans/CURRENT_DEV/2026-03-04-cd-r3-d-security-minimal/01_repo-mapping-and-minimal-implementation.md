# C/D线路 R3 - D仓安全与供应链最小实现（2026-03-04）

## 1) Repo-level 映射（D线 Must 对照）

D线 Must（参考包）：
- CI 纳入 `SAST/DAST + 依赖漏洞扫描 + secret scanning`
- 最小权限与密钥轮换
- provenance 与签名验证

当前仓库（落地前）现状：
- 已有 CI 主工作流：`.github/workflows/backend-tests.yml`
- 已有基础测试门禁：`unit/integration/coverage/docker`
- 已补入（已有草稿改动）依赖漏洞 + secret scanning：`pip-audit` + `gitleaks`
- 缺口：
  - 无 SAST 作业
  - 无 DAST 作业
  - 无 provenance/签名流程占位
  - 无最小权限与密钥轮换的统一落盘策略说明

## 2) 最小实现（本次）

### 2.1 CI 最小补齐（可回滚）

文件：`.github/workflows/backend-tests.yml`
- 保留并沿用 `security-baseline-check`：
  - `pip-audit -r main/backend/requirements.txt`
  - `gitleaks/gitleaks-action@v2`
- 新增 `sast-check`：
  - `bandit -r main/backend/app -q`
- 新增 `dast-check`（非 PR 触发）：
  - `docker compose` 启动后端
  - `OWASP ZAP baseline` 扫描 `http://127.0.0.1:8000`
- 新增 `provenance-signature-placeholder-check`：
  - 调用 `scripts/security/verify_provenance_placeholder.sh artifacts/release`

### 2.2 provenance/签名占位脚本（可观测）

文件：`scripts/security/verify_provenance_placeholder.sh`
- 若 `artifacts/release` 不存在：输出 skip 信息并退出 0（不阻塞现有流程）
- 若存在制品：要求每个制品具备同名 `.sig` 与 `.intoto.jsonl` sidecar
- sidecar 缺失时失败退出，提供最小可执行约束

### 2.3 最小权限与密钥轮换（文档约束）

本轮执行策略：
- 新增安全作业都显式声明 `permissions: contents: read`
- 扫描只使用平台默认 `GITHUB_TOKEN`
- 密钥轮换策略（最小）：季度轮换；疑似泄露立即轮换；轮换记录写入变更日志/发布记录

## 3) 参考包映射说明（Research note）

- `OWASP Top10 / ASVS`：
  - SAST + DAST 基线覆盖“输入处理、配置错误、已知漏洞组件”等高频风险入口
- `NIST SSDF`：
  - CI 中持续执行漏洞与秘密扫描，满足“自动化安全验证”与“供应链风险识别”的最小实践
- `SLSA`：
  - 本次先落地 provenance/signature 占位契约（`.intoto.jsonl` + `.sig`），后续可平滑接入正式签名与验证

## 4) 最小验证步骤

```bash
# 1) 工作流语法（YAML 解析）
python3 -m pip install --quiet pyyaml
python3 - <<'PY'
import yaml
with open('.github/workflows/backend-tests.yml', 'r', encoding='utf-8') as f:
    yaml.safe_load(f)
print('workflow yaml: ok')
PY

# 2) 占位脚本语法
bash -n scripts/security/verify_provenance_placeholder.sh

# 3) 占位脚本运行（无制品目录应可跳过通过）
bash scripts/security/verify_provenance_placeholder.sh artifacts/release
```

## 5) 回滚点

- 可逆步骤（未提交场景）：
```bash
git checkout -- .github/workflows/backend-tests.yml \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-cd-r3-d-security-minimal/01_repo-mapping-and-minimal-implementation.md
rm -f scripts/security/verify_provenance_placeholder.sh
```

- 若后续提交，回滚点为对应 commit hash。

## 6) R4（D线）继续执行记录（2026-03-04）

最小增量（本轮）：
- 在 `dast-check` 增加失败诊断产物，失败时上传 `docker compose` 进程与日志，提升安全门禁可观测性。

本轮执行验证：
- `python3 - <<'PY' ... yaml.safe_load('.github/workflows/backend-tests.yml') ... PY` -> `workflow yaml: ok`
- `bash -n scripts/security/verify_provenance_placeholder.sh` -> `ok`
- `bash scripts/security/verify_provenance_placeholder.sh artifacts/release` -> `artifact dir not found ... skip enforcement`（符合占位契约）
- `cd main/backend && python3 -m pytest tests/unit/test_minimal_rag_unittest.py -q` -> `4 passed`

next-batch-trigger（原子化）：
1. 当仓库出现真实 release artifacts（`artifacts/release/*`）时，触发“R5-签名与 provenance 强制校验”，将占位检查升级为阻断策略。
2. 当 `dast-check` 连续 3 次失败且失败点集中在服务启动阶段时，触发“R5-DAST 启动稳定性专项”（健康检查重试/依赖启动顺序/compose profile 收敛）。
3. 当 `pip-audit` 出现高危漏洞（high/critical）时，触发“R5-依赖应急修复批次”（锁版本、补丁升级、回归 smoke）。
