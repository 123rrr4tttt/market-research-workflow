# SA3-R3-F 最小落地实施记录（llm-report / 数据AI线）

日期：2026-03-04（PST）
范围：仓库 F（`llm-report` 数据AI线）

## 1. Repo-level 映射（快速）

- 代码主路径：`main/backend`
- 规范与文档入口：`README.md`、`main/backend/docs/`、`development/latest-dev-docs/`
- CI 门禁入口：`.github/workflows/backend-tests.yml`
- 本地测试入口：`main/backend/pytest.ini` + `python -m pytest`

### 与数据治理/AI工程（F线）相关薄弱点

1. `llm-report` 已有离线质量门禁函数（`evaluate_report_gate`），但缺少专门的最小制度化执行入口（固定检查脚本）。
2. `llm-report/generate` 未写入统一任务监控表（`EtlJobRun`），在线可观测与追溯不完整。
3. 缺少配置化回滚开关（只能依赖代码回退或部署回滚）。
4. API 对 `topic` 空白字符串校验不严格，可能下沉到服务层异常。

## 2. Must 最小集实现（小步、可回滚）

### 2.1 可追溯与在线监控

- 在 `llm-report` API 接入 `start_job/complete_job/fail_job`。
- 统一 `job_type=llm_report_gen`，记录 `topic/source_count_requested/gate_mode/trace_id`。
- 回写 `quality_gate` 关键结果（`decision/gate_version/pass/citation_coverage/evidence_coverage`）。

### 2.2 上线门禁（离线评估 + 在线门禁）

- 新增配置：
  - `llm_report_enabled`（总开关）
  - `llm_report_gate_mode`（`off|warn|strict`）
- `strict` 模式下，当 `quality_gate.decision=fail` 时阻断请求（422）。
- 单测新增 Must 基线样例：`pass/warn/fail` 三类固定决策。

### 2.3 回滚策略（最小）

- 软回滚（首选，无需回滚代码）：
  - `LLM_REPORT_GATE_MODE=warn`：保留生成，放宽阻断。
  - `LLM_REPORT_ENABLED=false`：临时关闭 llm-report 入口。
- 硬回滚：使用 git commit 回退（见本文末回滚点）。

## 3. 参考包映射（reference_pack / research_note -> 本仓库改动）

> 假设：仓库内未发现显式 `reference_pack/`、`research_note/` 目录，以下采用现有 F 线参考文档作为“参考包代理”。

| 参考来源（代理） | 对应要点 | 本次落地位置 |
|---|---|---|
| `development/latest-dev-docs/root-plans/F_PLAN/llm-report-best-practices-2026-03-03.md` | 报告质量门禁与可追溯要求 | `main/backend/app/api/llm_report.py`、`main/backend/tests/unit/test_llm_report_generator_unittest.py` |
| `main/backend/docs/version-F-llm-report-delivery-2026-03-03.md` | Version F 交付目标（结构化报告+质量门禁） | 本次扩展为“可观测+可回滚”最小制度化 |
| `.github/workflows/backend-tests.yml` + `README.md` | 现有 CI/测试门禁体系 | 新增最小检查脚本 `main/backend/scripts/check_llm_report_must_minset.py` 并纳入本地验证路径 |

## 4. 改动文件列表

1. `main/backend/app/api/llm_report.py`
2. `main/backend/app/settings/config.py`
3. `main/backend/app/services/llm_report_generator.py`
4. `main/backend/tests/unit/test_llm_report_api_unittest.py`
5. `main/backend/tests/unit/test_llm_report_generator_unittest.py`
6. `main/backend/scripts/check_llm_report_must_minset.py`
7. `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-sa3-r3-f-llm-report-must-minset/01_sa3-r3-f-implementation-2026-03-04.md`
8. `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
9. `development/latest-dev-docs/development-plans/INDEX.md`
10. `development/latest-dev-docs/README.md`
11. `development/latest-dev-docs/MERGED_OVERVIEW.md`

## 5. 最小验证命令与结果

执行目录：仓库根目录

```bash
python3 main/backend/scripts/check_llm_report_must_minset.py
```

```bash
cd main/backend && python3 -m pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py
```

执行结果：

- `python3 main/backend/scripts/check_llm_report_must_minset.py` -> `9 passed, 5 skipped`
- `cd main/backend && python3 -m pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py` -> `9 passed, 5 skipped`

## 6. 回滚点

- 基线回滚点（改动前 HEAD）：`c4f89bfc9f8bfd60ed793d56c11d2e87cc4c3a67`
- 建议回滚命令：

```bash
git reset --hard c4f89bfc9f8bfd60ed793d56c11d2e87cc4c3a67
```

> 若仅回滚本次改动文件，建议改用 `git checkout c4f89bfc9f8bfd60ed793d56c11d2e87cc4c3a67 -- <files...>` 精确回退。
