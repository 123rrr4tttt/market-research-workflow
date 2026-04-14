# 链路1：Ingest & Workflow Orchestration 平台化上位替代参考池

## 1) 本项目现状链路图（简版）

基于 `main/backend/app/api/ingest.py`、`main/backend/app/services/collect_runtime`、`main/backend/app/services/tasks.py`、`README.md`，当前主链路可抽象为：

```text
[Client/API Caller]
   -> POST /api/v1/ingest/* (ingest.py)
      输入: query_terms/urls/max_items/async_mode/project_key...
      |
      |-- async_mode=false: 直接调用 services.ingest/* 或 collect_runtime.run_collect
      |
      |-- async_mode=true: tasks.*.delay(...) 入 Celery
             -> Redis (broker)
             -> Celery Worker 执行 task_ingest_market / task_collect_policy_regulation / task_run_source_library_item ...
             -> collect_runtime.collect_request_from_* 构造 CollectRequest
             -> collect_runtime.run_collect() 按 channel 分发
                -> adapters(search.market/search.policy/source_library/url_pool/crawler.scrapy)
                -> ingest 子模块抓取/抽取/写入
             -> PostgreSQL(EtlJobRun + 业务表) / Elasticsearch(index)
             -> API 返回 task_id 或同步结果(inserted/updated/skipped/meta)
```

现状特征（用于后续平台化判断）：
- 编排核心是 `Celery + Redis`，任务定义集中在 `tasks.py`。
- 采集执行核心是 `CollectRequest/CollectResult + adapter`（`collect_runtime/runtime.py`）。
- API 层已内置同步/异步双路径（`async_mode`），具备做“绞杀式迁移”的入口条件。

---

## 2) 开源上位替代参考池（4+1）

> 满足约束：
> - `Temporal`（满足 Temporal/Airflow 二选一）
> - `Redpanda`（满足 Kafka/Pulsar/Redpanda 二选一）
> - `Dagster`（满足 Dagster/Prefect 二选一）

| 候选平台 | GitHub | 为何适配当前链路 | 替换成本（粗粒度） |
|---|---|---|---|
| Temporal | https://github.com/temporalio/temporal | 把 `tasks.py` 中分散 Celery task 升级为 durable Workflow + Activity；天然支持重试、超时、补偿、长事务，适配 `ingest -> collect -> index` 这类跨步骤链路。 | 中-高：需重写任务编排语义（task->workflow/activity），但业务采集函数可复用。 |
| Redpanda | https://github.com/redpanda-data/redpanda | 作为事件总线替代/增强 Redis 队列，适合 ingest 高并发削峰与异步解耦；Kafka API 兼容，便于后续生态接入。 | 中：需引入 topic 设计、consumer group、幂等键；任务执行代码可逐步保留。 |
| Dagster | https://github.com/dagster-io/dagster | 将 `collect_runtime` 抽象成 asset/op，强化可观测性、分区回填、任务 lineage；适合“数据采集+处理+索引”的数据工程编排。 | 中：需将现有函数包装为 ops/assets，调度和部署模型发生变化。 |
| Airbyte | https://github.com/airbytehq/airbyte | 对标准化外部源（API/DB/SaaS）可用 connector-first 方式替代部分自研 adapter，减少 connector 维护成本。 | 中：仅替换“标准连接器可覆盖”的子链路，长尾采集仍需自研。 |
| Apache NiFi（备选） | https://github.com/apache/nifi | 可视化 flow 编排、路由、限流、重试适合 ingestion control plane；用于把非核心抓取流从代码层外移。 | 中-高：需建设流程模板与运维规范，开发范式从 code-first 向 flow-first 转变。 |

建议优先组合：
- 主路径：`Temporal + Redpanda`
- 数据资产治理补位：`Dagster`
- 标准连接器补位：`Airbyte`

---

## 3) 代码/IO 级映射表（当前模块 -> 候选平台组件 -> 迁移策略）

| 当前模块（代码/IO） | 候选平台组件 | 迁移策略 |
|---|---|---|
| `app/api/ingest.py`：接收 `async_mode`、`query_terms/max_items/project_key`，返回同步结果或 `task_id` | Temporal Client / Dagster GraphQL or Run API 触发层 | **绞杀式**：保留原 API 契约；新增 `orchestrator_provider`（celery/temporal/dagster）开关，逐端点切流。 |
| `app/services/tasks.py`：Celery task 定义、retry、状态映射、crawler 编排 | Temporal Workflow + Activity（或 Dagster job + op） | **并行双写**：关键任务先 shadow run（新旧编排同时执行但仅旧链路写主结果），比对 `inserted/updated/skipped/errors` 一致性。 |
| `app/services/collect_runtime/runtime.py`：`CollectRequest` 构建、channel 分发、auto-batch 合并 | Dagster ops/assets 或 Temporal Activities（保留现有 Python 业务函数） | **绞杀式**：先保持 runtime 不动，只替换“谁来调 runtime”；稳定后再拆分 runtime 为更细粒度组件。 |
| `app/services/collect_runtime/adapters/*`：多 channel 抓取适配（search/source_library/url_pool/crawler） | Airbyte Connector（可覆盖源）+ 自研 Activity/Op（长尾源） | **一次迁移（按源）**：对“可标准化源”一次性迁到 Airbyte；非标准源维持现有 adapter。 |
| Redis Broker + Celery Queue（README 指定） | Redpanda topic + consumer group | **并行双写**：先“Celery 继续执行 + Redpanda 旁路投递”验证吞吐/延迟，再切换消费主链路。 |
| `EtlJobRun` 状态与任务追踪（tasks.py 中 `update_job_tracking/fail_job`） | Temporal Visibility / Dagster run metadata + 本地审计表 | **绞杀式**：先保留 `EtlJobRun` 作为统一审计面，新平台运行 ID 回填到 `params/meta`，避免观测断层。 |

---

## 4) 最小 PoC 命令集（可执行）

以下命令用于快速验证“编排层可替代性”，建议在独立目录执行。

### 4.1 Temporal 最小 PoC（本机 dev server + Python SDK）

```bash
# 1) 启动 Temporal dev server
brew install temporal
temporal server start-dev
```

```bash
# 2) 安装 Python SDK（另开终端）
python -m venv .venv && source .venv/bin/activate
python -m pip install -U pip temporalio
```

```bash
# 3) 用现有项目函数包装一个 Activity/Workflow（示例骨架）
# 假设文件在 /tmp/temporal_poc.py，执行：
python /tmp/temporal_poc.py
```

### 4.2 Redpanda 最小 PoC（本机 topic 验证）

```bash
brew install redpanda-data/tap/redpanda
rpk container start -n 1
rpk topic create ingest.jobs
rpk topic produce ingest.jobs -k demo -m '{"job":"market_ingest","project_key":"demo_proj"}'
rpk topic consume ingest.jobs -n 1
```

### 4.3 Dagster 最小 PoC（本机 job 编排）

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -U pip dagster dagster-webserver
mkdir -p /tmp/dagster_poc && cd /tmp/dagster_poc
dagster project scaffold --name ingest_poc
cd ingest_poc
dagster dev
```

### 4.4 Airbyte 最小 PoC（本机安装与状态验证）

```bash
brew install airbytehq/tap/abctl
abctl local install --low-resource-mode
abctl local status
abctl local credentials
```

---

## 5) 风险与回滚策略

| 风险 | 触发信号 | 回滚策略 |
|---|---|---|
| 新旧编排结果不一致（计数、错误集合） | shadow run 比对失败率上升 | 立即切回 `orchestrator_provider=celery`，保留新链路只读观测，不写主结果。 |
| 消息语义变化导致重复消费/漏消费 | Redpanda consumer lag 异常、幂等冲突上升 | 回退到 Celery 主消费；Redpanda 保留旁路镜像；按 `project_key+task_signature` 做幂等补偿。 |
| 任务状态面板断层（运维不可见） | `EtlJobRun` 与新平台 run_id 无法关联 | 强制双写 run_id 映射表；若映射失败，阻断切流并回滚。 |
| 平台运维复杂度上升 | 部署失败率、恢复时间（MTTR）变差 | 分阶段引入（先 Temporal，再 Redpanda）；每阶段保留“一键切回 Celery”开关。 |
| 采集源迁移导致覆盖率下降 | 连接器成功率/抓取覆盖指标下降 | 只迁“标准源”；长尾源继续走现有 adapter，避免一次性替换。 |

建议的切换闸门（Gate）：
- Gate 1：连续 7 天 shadow run，一致性 >= 99.5%。
- Gate 2：单项目灰度（1-2 个 project_key）稳定 1 周。
- Gate 3：全量切换后保留 2 周快速回滚窗口。

---

## 官方参考链接（优先 README/官方文档）

- Temporal（GitHub）：https://github.com/temporalio/temporal
- Temporal Python SDK（GitHub）：https://github.com/temporalio/sdk-python
- Temporal dev server 启动（官方）：https://temporal.io/setup/start-development-server
- Redpanda（GitHub）：https://github.com/redpanda-data/redpanda
- Redpanda `rpk container start`（官方文档）：https://docs.redpanda.com/23.3/reference/rpk/rpk-container/rpk-container-start/
- Dagster（GitHub）：https://github.com/dagster-io/dagster
- Airbyte（GitHub）：https://github.com/airbytehq/airbyte
- abctl（GitHub）：https://github.com/airbytehq/abctl
- Apache NiFi（GitHub）：https://github.com/apache/nifi

> 以上链接于 2026-03-04（US/Pacific）核验可访问。
