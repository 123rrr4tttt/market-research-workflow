# 封口文档（Closing Doc）- A线第4轮

日期：2026-03-03  
轮次：A线第4轮（夜间连续迭代）

## 1. 范围

- 主题：CI稳定性 / 回归可靠性 / Flake治理。
- 流程：已执行“先检索再落盘 -> 原子任务表 -> 实施 -> 验证 -> 封口”。
- 约束：以最小可回滚改造为主，不触达业务功能逻辑。

## 2. 本轮改动

### 文档与知识池
- `信息源库/CI-稳定性-回归可靠性-Flake治理-最佳实践-实施版-2026-03-03-round4.md`
- `.../05_A-line-round4-research-and-implementation-plan-CI-regression-flake-2026-03-03.md`
- `.../06_A-line-round4-atomic-task-table-and-gates-2026-03-03.md`
- `.../07_A-line-round4-closing-2026-03-03.md`
- 更新：`.../index.md`、`.../README.md`

### 代码与CI
- `.github/workflows/backend-tests.yml`
  - unit/integration lane 排除 flaky marker。
  - 新增 `flaky-observe` 非阻塞观察 job。
  - 引入 `PYTHONHASHSEED=0` 稳定运行环境。
- `main/backend/pytest.ini`
  - 新增 `flaky` marker。
- `main/backend/scripts/flake_report.py`
  - 将 flaky lane 的 junit 结果转换为 markdown 摘要。
- `main/backend/tests/quarantine/README.md`
  - 建立 quarantine 使用规范。
- `main/backend/tests/unit/test_flake_report_unittest.py`
  - 覆盖 flake report 脚本的关键路径。

## 3. 验证证据（pass / skip / fail）

| 验证项 | 结果 | 证据 |
|---|---|---|
| 最佳实践来源落盘（含链接/边界/步骤/风险回滚） | PASS | 知识池文档与 05 文档已写入 |
| 原子任务与门禁表产出 | PASS | 06 文档包含依赖、并行组、门禁、负责人、产物 |
| CI 改造落地 | PASS | backend-tests.yml 已新增 flaky observe lane 并调整 deterministic lane |
| flake 报告脚本可执行性 | PASS | 新增单测覆盖 summarize/render |
| 本地测试验证 | PASS | `python3 -m pytest tests/unit/test_flake_report_unittest.py tests/unit/test_streamplus_contracts_unittest.py -q` => `6 passed` |
| 全量 CI / e2e 回归 | SKIP | 本轮未在本地执行全量流水线（成本与时间限制） |
| 失败项 | FAIL=0 | 无 |

## 4. 回滚点

可按文件粒度回滚以下路径：
- `.github/workflows/backend-tests.yml`
- `main/backend/pytest.ini`
- `main/backend/scripts/flake_report.py`
- `main/backend/tests/quarantine/README.md`
- `main/backend/tests/unit/test_flake_report_unittest.py`
- 第4轮文档与索引更新文件

若使用 git：回退至本轮前提交点即可一次性撤销。

## 5. 剩余风险

1. flaky marker 仍需 owner + issue 绑定，否则可能长期滞留观察区。  
2. 当前仅新增观察层，还未建立“自动晋升/降级”机制。  
3. 尚未执行真实 CI 多日观测，flake 基线数据不足。

## 6. 下一轮衔接

1. 给每个 flaky 用例绑定 owner/SLA/退出标准。  
2. 增加 flaky 趋势统计（按周 top N、失败类型分层）。  
3. 基于 1-2 周数据决定是否提升部分测试回主门禁。
