<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-04-cd-r3-c-observability-minimal/01_repo-mapping-and-minimal-implementation.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-cd-r3-c-observability-minimal/01_repo-mapping-and-minimal-implementation.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# C/D线路 R3 — C仓可观测性最小实现（2026-03-04）

## 1) Repo-level 映射（C线 Must 对照）

参考包对照（C线 Must）：
- request_id/trace_id 贯通
- 核心用户旅程 SLI/SLO
- 告警分级和值班响应流程文档化

当前仓库现状：
- 已具备 request_id 基础：`main/backend/app/main.py` 的 `metrics_middleware` 生成/透传 `X-Request-Id`，并写入请求日志。
- 已具备基础 metrics：`/metrics` 暴露 `REQUEST_COUNT` / `REQUEST_LATENCY`。
- 缺口：
  - request_id / trace_id 透传已有自动化测试断言（防漂移）。
  - 缺少“核心旅程 SLI/SLO + 告警分级值班流程”的最小文档门禁资产。

## 2) 最小实现

- 代码最小增量：
  - 文件：`main/backend/tests/integration/test_api_exception_envelope_unittest.py`
  - 新增测试：`test_request_id_is_echoed_for_observability_correlation`
  - 目标：锁定 request_id 相关性行为（请求头 -> 响应头），避免后续重构回归。

- 文档最小资产（本文件）：
  - 明确 C线 Must 在本仓的现状、缺口、落地顺序。
  - 约束本轮只做“可验证最小增量”，不引入大规模组件变更。

## 3) SLI/SLO 与告警分级（最小草案）

核心旅程（MVP）：`POST /api/v1/discovery/search`
- SLI-1 可用性：5xx 比例
- SLI-2 时延：p95 latency
- SLO 建议（初版）：
  - 可用性：>= 99.5%（7天窗口）
  - p95 时延：< 800ms（7天窗口）

告警分级（最小）：
- P1：可用性 SLO 严重违约或核心接口不可用（立即值班响应）
- P2：p95 时延连续超阈值（工作时段快速处理）
- P3：噪音类或短时抖动（观察+排队修复）

值班流程（最小）：
1. 触发 -> 记录 request_id/时间窗
2. 定位 -> 对照日志与 metrics
3. 缓解 -> 回滚或降级
4. 复盘 -> 更新阈值/规则

## 4) 验证

建议命令：
```bash
cd main/backend
python3 -m pytest tests/integration/test_api_exception_envelope_unittest.py -q
```

本轮目标验证点：
- 新增 request_id 相关性测试通过。
- 既有异常 envelope 测试不回归。

2026-05-23 复核补充：

- `main/backend/tests/integration/test_api_exception_envelope_unittest.py`
  已包含 `test_request_id_is_echoed_for_observability_correlation`。
- `main/backend/tests/e2e/test_request_context_headers_e2e.py`
  已覆盖 `X-Trace-Id` 响应头与 `traceparent` trace-id 提取。

## 5) 回滚点

- 代码回滚文件：
  - `main/backend/tests/integration/test_api_exception_envelope_unittest.py`
- 文档回滚文件：
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-cd-r3-c-observability-minimal/01_repo-mapping-and-minimal-implementation.md`

若需快速回滚：
```bash
git checkout -- main/backend/tests/integration/test_api_exception_envelope_unittest.py \
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-04-cd-r3-c-observability-minimal/01_repo-mapping-and-minimal-implementation.md
```
