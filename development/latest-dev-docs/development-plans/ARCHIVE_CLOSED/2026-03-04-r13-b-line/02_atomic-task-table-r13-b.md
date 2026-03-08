# R13 B线原子任务表（M1）

- date: 2026-03-04
- scout_batch_id: `2026-03-04-scout-r13`
- task_id: `B-R13-M1`
- goal: required checks 与 ruleset 命名冻结（warning 灰度）
- scope: 仅 B 线仓库最小原子切片；本轮仅 M1 + 机读产物 + ver 证据 + rollback 点

research:
- Workflow source-of-truth: `.github/workflows/backend-tests.yml`.
- Required check gate job: `gateplus-required-check`.
- Required tuple found in workflow convergence step: `("standards-check", "gateplus-guard-check", "r81-b-min-verify-check")`.
- Repo local ruleset file (`ruleset*.json|yaml|toml`) not found; ruleset alignment remains warning.

plan:
- Reuse and minimally extend `scripts/governance/emit_required_check_freeze.py` for R13 metadata and `drift_count` output.
- Emit machine-readable artifact to:
  - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r13_b/ruleset-checks-lock.json`
- Keep warning-only (`blocking_enabled=false`) this round; do not include high-volatility jobs in required checks.
- Failure isolation stays in governance PR check contract only.

atomic:
- 原子任务并行序列:
  - P1 (parallel):
    - AT1: 从 workflow 提取 required tuple。
    - AT2: 提取 required gate 名称并计算 ruleset/workflow 对齐状态。
  - P2 (serial):
    - AT3: 生成 R13 机读 JSON（含 required checks、alignment、drift_count、failure isolation）。
- Changed files:
  - `scripts/governance/emit_required_check_freeze.py`
  - `artifacts/gates/r13_b/ruleset-checks-lock.json`

ver:
- Repro command 1:
  - `python3 /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/scripts/governance/emit_required_check_freeze.py --mode warning --task-id B-R13-M1 --scout-batch-id 2026-03-04-scout-r13 --out /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r13_b/ruleset-checks-lock.json`
- Repro command 2:
  - `python3 -m json.tool /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r13_b/ruleset-checks-lock.json >/dev/null`
- Result summary:
  - emitter exit code: `0`
  - JSON validation: `pass`
  - `alignment.workflow.status`: `pass`
  - `alignment.ruleset.status`: `warn`
  - `drift_count`: `1`

close:
- output_artifact:
  - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r13_b/ruleset-checks-lock.json`
- gray_strategy:
  - warning only; blocking delayed to later stabilization cycle.
- failure_isolation:
  - only governance PR required-check contract; no expansion to other lanes.
- rollback_ref:
  - `0b54e98b6e72bbe3e2e0b14e576f5b5a43ea9e05`
