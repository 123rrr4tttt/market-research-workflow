# R12 A线 M1 Implementation & Verification（2026-03-04）

## research
- 输入 handoff：`/Users/wangyiliang/Desktop/openclaw/docs/reference-pool/2026-03-04-scout-r12/codex_handoff.md`
- 现状：A 线已有 flaky trend 链路与 gate JSON，但未固化 `flake-budget.json` 三指标命名。
- M1 范围：仅实现预算计算与 warning 灰度接线；不做 blocking。

## plan
- 改造 `flake_trend.py`：统一输出 `flake_rate`、`rerun_pass_rate`、`test_determinism_score`。
- 改造 `check_flake_trend_thresholds.py`：新增 `--mode warning|blocking`，warning 下不返回失败码。
- 改造 `backend-tests.yml`：生成 `flake-budget.json` 并发布到 summary/artifacts。
- 补单测并执行最小验证。

## atomic
- 已执行改动：
  - `main/backend/scripts/flake_trend.py`
  - `main/backend/scripts/check_flake_trend_thresholds.py`
  - `main/backend/tests/unit/test_flake_trend_unittest.py`
  - `main/backend/tests/unit/test_check_flake_trend_thresholds_unittest.py`
  - `.github/workflows/backend-tests.yml`
- 原子任务并行序列：
  - Phase P1（并行实现）：`[trend-metrics, gate-warning-mode, workflow-artifact]`
  - Phase P2（串行收口）：`[unit-test, artifact-materialization, doc-close]`

## ver
- 可复现实命令：
```bash
cd /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-A/main/backend
python3 -m pytest -q tests/unit/test_flake_trend_unittest.py tests/unit/test_check_flake_trend_thresholds_unittest.py
mkdir -p artifacts/history
cp artifacts/flake_r4_junit.xml artifacts/history/flaky-junit-r4.xml
python3 scripts/flake_trend.py --junit-glob "artifacts/history/*.xml" --output artifacts/flaky-trend-report.md --output-json artifacts/flaky-trend-summary.json --top-n 15 --threshold 0.30
python3 scripts/check_flake_trend_thresholds.py --summary-json artifacts/flaky-trend-summary.json --output-json artifacts/flaky-trend-gate.json --max-above-threshold 0 --min-tests 1 --mode warning
mkdir -p artifacts/gates/r12_a ../../artifacts/gates/r12_a
python3 - <<'PY'
from __future__ import annotations
import json
from pathlib import Path
summary = Path('artifacts/flaky-trend-summary.json')
payload = json.loads(summary.read_text(encoding='utf-8'))
budget = payload.get('budget', {})
out = {
  'mode': 'warning',
  'blocking': False,
  'flake_rate': budget.get('flake_rate', 0.0),
  'rerun_pass_rate': budget.get('rerun_pass_rate', 0.0),
  'test_determinism_score': budget.get('test_determinism_score', 0.0),
  'source_summary_json': str(summary),
}
for p in [Path('artifacts/gates/r12_a/flake-budget.json'), Path('../../artifacts/gates/r12_a/flake-budget.json')]:
  p.write_text(json.dumps(out, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
PY
```
- 结果摘要：
  - 单测：`11 passed in 0.03s`
  - gate：`status=warn`，`reason=above_threshold_exceeded`，退出码 `0`（warning 灰度）
  - 机读工件（绝对路径）：
    - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-A/artifacts/gates/r12_a/flake-budget.json`
  - 三指标值：
    - `flake_rate=0.2`
    - `rerun_pass_rate=0.8`
    - `test_determinism_score=0.8`

## close
- rollback_ref: `400beb9f7d3dd10940daabdb7deea0bed3f2bd14`
- runtime_fingerprint:
  - time: `2026-03-04 02:40:58 PST`
  - os: `Darwin 25.3.0 arm64`
  - python: `Python 3.9.6`
