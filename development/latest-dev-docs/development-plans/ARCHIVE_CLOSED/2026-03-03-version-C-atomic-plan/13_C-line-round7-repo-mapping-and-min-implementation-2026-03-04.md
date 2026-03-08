# C线第7轮：Repo-Level映射与最小实现（2026-03-04）

## 1. Repo-Level 映射（现状）

### 1.1 request_id / trace_id 现状
- `main/backend/app/main.py` 已有 `metrics_middleware`，可生成/透传 `X-Request-Id`，并把请求日志统一写入 `app.request`。
- API envelope 的 `meta.trace_id` 已存在（`main/backend/app/contracts/responses.py`），但 trace 来源此前主要依赖 `X-Request-Id`。
- `/metrics` 已暴露 Prometheus 指标（请求计数、时延 histogram）。

### 1.2 可靠性与健康检查现状
- 轻量健康检查：`GET /api/v1/health`。
- 深度健康检查：`GET /api/v1/health/deep`（DB + Elasticsearch）。
- Docker/脚本侧已有健康检查调用（`scripts/docker-deploy.sh`, `main/ops/start-all.sh` 等）。

### 1.3 文档现状
- 可观测性相关散见于接口/规划文档，缺少一份面向值班和告警执行的最小统一模板（SLI/SLO + 分级 + 值班流程）。

## 2. 缺口识别（对照 C线 Must）

- Must-1：`request_id/trace_id` 贯通  
  缺口：未统一支持 `X-Trace-Id` 与 `traceparent` 解析，响应头缺少 `X-Trace-Id` 明确回传。
- Must-2：核心用户旅程 SLI/SLO  
  缺口：缺少仓库内可直接复用的最小 SLI/SLO 基线模板。
- Must-3：告警分级和值班流程文档化  
  缺口：缺少统一告警分级与值班处置模板（含升级规则）。

## 3. 最小实现（本次落地）

### 3.1 代码最小改动
- 文件：`main/backend/app/main.py`
- 改动点：
  - 新增 `traceparent` 解析（W3C trace context 的最小字段校验）。
  - 新增 trace/request 解析逻辑：
    - `trace_id` 优先级：`X-Trace-Id` -> `traceparent.trace-id` -> `X-Request-Id/自动生成 request_id`。
    - `request_id` 保持现有兼容逻辑（`X-Request-Id` 或 UUID）。
  - 响应头新增 `X-Trace-Id`。
  - contract envelope / error payload 的 `meta.trace_id` 改为统一使用解析后的 `trace_id`。

### 3.2 测试最小补充
- 文件：`main/backend/tests/e2e/test_request_context_headers_e2e.py`
- 新增用例：
  - `X-Trace-Id` 透传回响应头。
  - 仅传 `traceparent` 时，响应头 `X-Trace-Id` 使用解析出的 trace-id。

### 3.3 文档最小补充
- 新增可执行模板文档：`development/latest-dev-docs/backend-core/E_OPS/OBSERVABILITY_RELIABILITY_BASELINE_2026-03-04.md`
  - 包含核心旅程 SLI/SLO（availability/latency/error/freshness）。
  - 告警分级（P1/P2/P3）和 on-call 流程（触发、升级、复盘）。

## 4. 参考包映射说明（Research -> Repo）

- OpenTelemetry（关键路径）  
  本次采用“无重依赖骨架”策略：先完成 `traceparent` 兼容与 `trace_id` 贯通，后续可平滑接入 OTel SDK（不会破坏当前 header 契约）。
- Prometheus  
  仓库已有 `/metrics` 与基础请求指标；本次将其纳入 SLI/SLO 文档模板作为默认数据源。
- Grafana  
  本次未引入新配置，先在文档定义面板最小字段（availability、p95、error rate）以支撑后续看板落地。
- SRE workbook  
  本次通过告警分级+值班流程+复盘模板形成最小 runbook 化入口。

## 5. 可回滚性

- 代码回滚范围集中在：
  - `main/backend/app/main.py`
  - `main/backend/tests/e2e/test_request_context_headers_e2e.py`
- 文档均为增量新增，可直接删除对应文件并回退索引引用。
