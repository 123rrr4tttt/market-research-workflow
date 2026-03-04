# SA3 R6.1 运行时基准统一（E线）

## 1) 统一运行时基准定义
- 统一 Python 入口：`main/backend/.venv311-fixed/bin/python`
- 统一 pytest 入口：`main/backend/.venv311-fixed/bin/pytest`
- 统一版本要求：Python `3.11.14`（满足 `>=3.10`，优先 3.11）
- 固定工作目录：`main/backend`

> 说明：仓内原有 `.venv311` 的 python 软链接指向 `cpython-3.11-macos-aarch64-none`（本机实际为 `cpython-3.11.14-...`），存在运行时漂移风险。

## 2) Runtime 指纹（执行证据）
- repo/backend: `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-E-db/main/backend`
- rollback 点（当前 commit）：`6a4277b`
- venv 路径：`main/backend/.venv311-fixed`
- Python：`Python 3.11.14`
- pytest：`pytest 9.0.2`
- 关键依赖：
  - `fastapi 0.115.0`
  - `SQLAlchemy 2.0.35`
  - `pydantic 2.9.2`

## 3) 固定测试命令（E）
```bash
cd /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-E-db/main/backend
.venv311-fixed/bin/pytest -q \
  tests/integration/test_deep_health_db_degraded_unittest.py \
  tests/unit/test_db_session_reliability_unittest.py
```

## 4) 关键测试补跑结果（E）
- deep-health（integration）：PASS
- db reliability（unit）：PASS
- 汇总：`9 passed, 13 warnings in 8.40s`
- 观察：本轮未出现 skip，已满足“优先解决 E 集成测试 skip”的稳定跑测目标。

## 5) 失败分类与修复
### 环境缺陷（已修复）
- 现象：原 `.venv311/bin/python` 软链接目标与本机实际 Python 安装路径不一致，导致运行时不稳定。
- 修复命令：
```bash
cd /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-E-db/main/backend
python3.11 -m venv .venv311-fixed
.venv311-fixed/bin/python -m pip install -U pip setuptools wheel
.venv311-fixed/bin/python -m pip install -r requirements.txt pytest
```
- 修复后重跑：PASS（见上）

### 代码缺陷
- 本次目标测试集未发现阻断性代码缺陷。

## 6) 回滚点
- Git 回滚锚点：`6a4277b`
- 文件级变更（本次）：新增 `docs/implementation/SA3-R6.1-runtime-baseline.md`

## 7) next-batch-trigger
满足以下任一条件触发下一批：
1. `.venv311` 被修复/重建后，切回统一入口并验证 `-m pytest` 全链路可用性；
2. 扩展跑测到 `integration` 全集（含 db/health 相关用例）；
3. 将统一基准命令固化进 `scripts/test-standardize.sh`（支持显式指定 `.venv311-fixed`）。
