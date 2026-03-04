# A线 Round7 执行记录（MVP：Flaky Trend 机器可读 Summary）

## 1. 目标
- 在 Round6 flaky trend 能力基础上，新增一个最小可验证工程化增量。
- 保持现有 markdown 报告链路不变，新增可机读 JSON summary 输出，供 CI/后续门禁策略消费。

## 2. 实施内容
- 脚本增强：`main/backend/scripts/flake_trend.py`
  - 新增可选参数 `--output-json`。
  - 新增 `build_summary(...)`，输出稳定 JSON schema：`totals / threshold / top_n / items`。
  - `main()` 在 `--output-json` 存在时落盘 JSON，不影响原 `--output` markdown 逻辑。
- 单测增强：`main/backend/tests/unit/test_flake_trend_unittest.py`
  - 新增 `test_build_summary_outputs_machine_readable_schema`。
  - 新增 `test_main_writes_optional_json_output`，验证 CLI 主流程能写出 JSON。
- CI 接入：`.github/workflows/backend-tests.yml`
  - 在 flaky trend 步骤新增 `--output-json artifacts/flaky-trend-summary.json`。

## 3. 验证
- 命令：
  - `cd main/backend && python3 -m pytest -q tests/unit/test_flake_trend_unittest.py tests/unit/test_flake_report_unittest.py tests/unit/test_validate_flaky_registry_unittest.py`
  - `cd main/backend && mkdir -p artifacts/history && cp artifacts/flaky-junit.xml artifacts/history/flaky-junit-current.xml 2>/dev/null || true && python3 scripts/flake_trend.py --junit-glob "artifacts/history/*.xml" --output artifacts/flaky-trend-report.md --output-json artifacts/flaky-trend-summary.json --top-n 15 --threshold 0.30`
  - `cd main/backend && python3 -m json.tool artifacts/flaky-trend-summary.json >/dev/null`
- 结果：通过（见本轮终端输出）。

## 4. 增量边界
- 本轮仅扩展 flaky trend 观测产物格式，不改主门禁判定，不改 flaky registry 规则。
- 改动保持低侵入，可按文件级回滚。

## 5. 风险与后续
- 当前 JSON 仅反映本次输入窗口（仍依赖 `artifacts/history/*.xml` 提供历史样本）。
- 后续可将阈值与窗口配置化，并接入历史窗口拉取能力，形成可追踪趋势链路。
