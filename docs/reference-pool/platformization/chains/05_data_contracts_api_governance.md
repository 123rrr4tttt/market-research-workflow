# 链路5：Data Contracts & API Governance 平台化参考池

日期：2026-03-04（US/Pacific）  
范围：`main/backend/app/contracts/*`、`main/backend/app/api/*`、`.github/workflows/backend-tests.yml`

## 1) 现状（envelope + error code + tests）

### 1.1 Envelope（统一响应包）
- 已有统一 envelope：`ApiEnvelope = {status, data, error, meta}`。实现位于：
  - `main/backend/app/contracts/responses.py`
  - `ok()` / `fail()` / `ok_page()` 作为主入口。
- 兼容层仍在：`success_response()` / `error_response()`（`main/backend/app/contracts/api.py`）标注为“transitional helper”，说明处于迁移并存期。
- API 层混用现象仍存在：
  - 一部分路由使用 `ok/fail`（如 `api/policies.py`、`api/resource_pool.py`、`api/crawler.py`）。
  - 一部分路由使用 `success_response/error_response`（如 `api/ingest.py`、`api/discovery.py`、`api/admin.py`）。
  - 少量路由仍抛 `HTTPException(detail=str)` 依赖全局异常包装兜底（多文件可见）。

### 1.2 Error Code（错误模型）
- 统一错误码枚举已存在（`ErrorCode`）：`INVALID_INPUT`、`PROJECT_KEY_REQUIRED`、`NOT_FOUND`、`CONFIG_ERROR`、`UPSTREAM_ERROR`、`PARSE_ERROR`、`RATE_LIMITED`、`INTERNAL_ERROR`。来源：`main/backend/app/contracts/errors.py`。
- 已有两层映射：
  - HTTP status -> ErrorCode：`map_status_to_error_code()`。
  - Exception -> ErrorCode/message/details：`map_exception_to_error()`（包含数据库类异常与关键字匹配）。
- 测试表明错误响应会回写 `x-error-code` 头，且保留 `detail` 兼容别名（详见 `main/backend/tests/core_business/test_main_core_contract.py`）。

### 1.3 Tests（契约相关测试与 CI）
- 已有契约测试资产：
  - 基础 contract helpers：`main/backend/tests/contract/test_contracts_unittest.py`
  - OpenAPI 结构快照：`main/backend/tests/contract/test_openapi_contracts_unittest.py`
  - 主程序异常包裹契约：`main/backend/tests/core_business/test_main_core_contract.py`
- 当前 `backend-tests` workflow 现状（`.github/workflows/backend-tests.yml`）：
  - 有 `standards-check`、`unit-check`、`integration-check`。
  - 但未显式单列 `contract-check`（如 `pytest -m "contract ..."`）。
- 结论：代码层已有契约模型雏形，但 CI 门禁对“契约变更”仍缺专门 required check。

## 2) 3-5 个开源替代（平台化工具链候选）

### 方案A：OpenAPI/JSON Schema 治理栈（REST 主线）
- Redocly CLI（OpenAPI lint/bundle）
- Spectral（规则引擎）
- openapi-diff（兼容性差异检测）
- 适配点：对当前 FastAPI OpenAPI 导出结果做“规范检查 + 破坏性变更拦截”。
- 链接：
  - https://github.com/Redocly/redocly-cli
  - https://github.com/stoplightio/spectral
  - https://github.com/OpenAPITools/openapi-diff

### 方案B：JSON Schema 契约校验栈（数据面）
- Ajv（高性能 JSON Schema validator）
- json-schema-diff（schema diff）
- 适配点：对 `ApiEnvelope` 与关键业务 payload 生成/维护 JSON Schema，做前后版本兼容校验。
- 链接：
  - https://ajv.js.org/
  - https://github.com/getsentry/json-schema-diff

### 方案C：Buf + Protobuf（跨服务 IDL 治理）
- Buf CLI（lint + breaking change check）
- Protobuf（请求/响应/事件统一 IDL）
- 适配点：如果后续引入 gRPC 或跨语言 SDK，Buf 可作为“破坏性变更门禁核心”。
- 链接：
  - https://buf.build/
  - https://github.com/bufbuild/buf
  - https://protobuf.dev/

### 方案D：AsyncAPI（事件契约治理）
- AsyncAPI spec + parser + generator
- 适配点：为 Celery/队列事件（queued/running/finished/failed）建立事件契约与文档，补齐当前“事件 schema 缺位”。
- 链接：
  - https://www.asyncapi.com/
  - https://github.com/asyncapi/spec
  - https://github.com/asyncapi/parser-js

### 方案E：Pact（消费者驱动契约测试）
- Pact（HTTP + message pact）
- Pact Broker（契约版本协作）
- 适配点：前后端/服务间接口发布前验证“消费者是否仍可用”。
- 链接：
  - https://pact.io/
  - https://github.com/pact-foundation/pact-js
  - https://github.com/pact-foundation/pact_broker

## 3) IO 级映射（request / response / event schema）

| IO层 | 当前实现 | 当前形态 | 治理缺口 | 建议目标 |
|---|---|---|---|---|
| Request Schema | `api/*` 内 `BaseModel`（如 `DiscoveryRequest`、`PolicyIngestRequest`、`MarketIngestRequest`）+ Query 参数 | 模型分散在各路由文件，命名与字段有历史兼容字段（如 `query_terms/keywords`、`max_items/limit`） | 复用度低，跨 API 一致性规则缺失 | 抽取 `contracts/schemas/requests/*`，建立字段别名和弃用策略（版本化） |
| Response Schema | `ApiEnvelope` + `ok/fail/ok_page` + 兼容层 `success_response/error_response` | envelope 统一方向明确，但 helper 并存，路由风格不一 | 迁移未收敛，response_model 覆盖不完整 | 强制路由声明 `response_model=ApiEnvelope[...]`；逐步移除 transitional helper |
| Error Schema | `ErrorCode` + `map_status_to_error_code` + `map_exception_to_error` | 错误码已统一，含 details；测试覆盖 `x-error-code` | 错误详情字段结构未标准化（业务子码/可重试语义不完全统一） | 建立 `error.details` 子结构规范（`retryable/category/subcode/context`）并做 schema 校验 |
| Event Schema | 异步返回多用 `task_result_response`；运行态散落于 job logger / Celery payload | 事实标准存在（`task_id/async/status/result/params`），但未形成显式事件规范 | 无统一事件 IDL，无版本策略，无兼容门禁 | 引入 AsyncAPI 或 Protobuf message，定义 `TaskQueued/TaskCompleted/TaskFailed` 事件契约 |

## 4) 门禁接入建议（CI required checks）

基于当前 `.github/workflows/backend-tests.yml`，建议把以下检查加入 required checks（PR 必过）：

1. `standards-check`（已存在，保留）
2. `unit-check`（已存在，保留）
3. `integration-check`（已存在，保留）
4. `contract-check`（新增）
   - 建议命令：`pytest -m "contract and not external and not flaky" -q`
5. `openapi-compat-check`（新增）
   - 导出基线 OpenAPI，与目标分支比较；禁止 breaking changes（如删字段、改 required、缩窄枚举）。
6. `schema-lint-check`（新增）
   - Spectral/Redocly 规则校验（命名、错误响应、分页元信息、deprecated 标记等）。
7. `pact-verify-check`（可选但推荐）
   - 有消费者后启用，验证 provider 对已发布 pact 的兼容性。

分阶段建议：先落 `contract-check + openapi-compat-check`，再接 `schema-lint` 与 `pact`。

## 5) 最小落地步骤

1. **收敛统一返回入口**  
   在新增/改动路由中只允许 `ok/fail/ok_page`，冻结 `success_response/error_response` 新增使用。

2. **补齐契约测试门禁**  
   在 `backend-tests.yml` 增加 `contract-check` job，并设为 required。

3. **引入 OpenAPI 兼容性检查**  
   生成 `openapi.json` 基线（主分支），PR 中执行 diff，发现 breaking 直接 fail。

4. **定义事件契约最小集**  
   先为 `task_result_response` 对应的三个关键状态（queued/finished/failed）产出 `event schema v1`。

5. **建立治理目录与版本策略**  
   在 `contracts/schemas/` 下按 `request/response/event` 分层并加版本号（`v1`），同时记录弃用窗口与迁移规则。

## 参考证据（仓内）
- `main/backend/app/contracts/responses.py`
- `main/backend/app/contracts/api.py`
- `main/backend/app/contracts/errors.py`
- `main/backend/app/contracts/tasks.py`
- `main/backend/app/contracts/schemas/policies.py`
- `main/backend/app/api/policies.py`
- `main/backend/app/api/discovery.py`
- `main/backend/app/api/ingest.py`
- `main/backend/tests/contract/test_contracts_unittest.py`
- `main/backend/tests/contract/test_openapi_contracts_unittest.py`
- `main/backend/tests/core_business/test_main_core_contract.py`
- `.github/workflows/backend-tests.yml`
