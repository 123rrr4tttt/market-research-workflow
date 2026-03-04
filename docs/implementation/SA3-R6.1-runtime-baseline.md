# SA3 R6.1 运行时基准统一（E/F 线）

## 1) 统一运行时基准定义
- 统一 Python 入口：`main/backend/.venv311-fixed/bin/python`
- 统一 pytest 入口：`main/backend/.venv311-fixed/bin/pytest`
- 统一版本要求：Python `3.11.14`（满足 `>=3.10`，优先 3.11）
- 固定工作目录：`main/backend`
- F 线补充：使用 `sh -lc` 注入 `PYTHONPATH=.`，确保 `app` 包可解析

> 说明：仓内原有 `.venv311` 的 python 软链接指向 `cpython-3.11-macos-aarch64-none`，与本机实际 `cpython-3.11.14-...` 存在漂移风险。

## 2) 通用 Runtime 指纹
- venv 路径：`main/backend/.venv311-fixed`
- Python：`Python 3.11.14`
- pytest：`pytest 9.0.2`
- 关键依赖：
  - `fastapi 0.115.0`
  - `SQLAlchemy 2.0.35`
  - `pydantic 2.9.2`

## 3) E 线执行证据
- repo/backend: `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-E-db/main/backend`
- rollback 点：`6a4277b`

### 固定测试命令（E）
```bash
cd /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-E-db/main/backend
.venv311-fixed/bin/pytest -q \
  tests/integration/test_deep_health_db_degraded_unittest.py \
  tests/unit/test_db_session_reliability_unittest.py
```

### 关键测试补跑结果（E）
- deep-health（integration）：PASS
- db reliability（unit）：PASS
- 汇总：`9 passed, 13 warnings in 8.40s`
- 观察：本轮未出现 skip，已满足“优先解决 E 集成测试 skip”的稳定跑测目标。

## 4) F 线执行证据
- repo/backend: `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-F-llm-report/main/backend`
- rollback 点：`f1579fc`

### 固定测试命令（F）
```bash
cd /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-F-llm-report/main/backend
sh -lc 'PYTHONPATH=. .venv311-fixed/bin/python scripts/check_llm_report_must_minset.py'
```

### 等价拆分命令（F）
```bash
cd /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-F-llm-report/main/backend
sh -lc 'PYTHONPATH=. .venv311-fixed/bin/pytest -q tests/unit/test_llm_report_generator_unittest.py tests/unit/test_llm_report_api_unittest.py'
```

### 关键测试补跑结果（F）
- must-check 脚本：PASS
  - gate metrics 可见：`gate_version, decision, hard_failures, soft_failures, missing_items, observability`
  - quality_gate_metrics 可见：`gate_version, decision, pass, hard_failure_count, soft_failure_count, citation_coverage, evidence_coverage, source_count, unique_citations, rules_count, gate_duration_ms`
- api/generator 单测：PASS
  - 汇总：`12 passed, 10 skipped, 4 warnings`

## 5) 失败分类与修复
### 环境缺陷
- E 线：原 `.venv311/bin/python` 软链接目标与本机实际 Python 安装路径不一致，已通过重建 `.venv311-fixed` 修复。
- F 线：除链接漂移外，还存在 `ModuleNotFoundError: app`，已通过 `sh -lc 'PYTHONPATH=.'` 统一入口绕过。

### 代码缺陷
- 本次目标测试集未发现阻断性代码缺陷。

## 6) 回滚点
- E 线 Git 回滚锚点：`6a4277b`
- F 线 Git 回滚锚点：`f1579fc`
- 文件级变更（本次）：新增 `docs/implementation/SA3-R6.1-runtime-baseline.md`

## 7) next-batch-trigger
满足以下任一条件触发下一批：
1. 将 `.venv311-fixed` 与 `PYTHONPATH=.` 固化进测试标准脚本，消除入口差异；
2. 扩展跑测到 `integration/contract` 全集，并复核当前 skipped 用例是否应转为可执行；
3. 将统一基准命令沉淀进标准化脚本，避免人工选择运行口径。
