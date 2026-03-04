# 链路4：Crawler & Source Library Runtime 平台化参考池

## 1) 现状链路（import / deploy / rollback / run-item）

### 1.1 Import（Crawler Project 导入）
- API：`POST /crawler/projects/import`
- 入口：`main/backend/app/api/crawler.py#import_crawler_project_api`
- 核心服务：`main/backend/app/services/crawlers_mgmt/service.py#import_project`
- 当前行为：
  - 规范化 `project_key/name/source_uri/provider`。
  - 生成版本号（`v<sha1前10位>`）并写入 `public.crawler_projects`。
  - 通过 heuristic/LLM 生成 `analysis_plan`（T00-T19 原子任务）。
  - 项目状态置为 `imported`。

### 1.2 Deploy（部署）
- API：`POST /crawler/projects/{project_key}/deploy`
- 入口：`main/backend/app/api/crawler.py#deploy_crawler_project_api`
- 核心服务：`main/backend/app/services/crawlers_mgmt/service.py#deploy_project`
- 编排任务：`task_orchestrate_crawler_deploy`（`main/backend/app/services/tasks.py`）
- 当前行为：
  - 创建 `public.crawler_deploy_runs` 记录（action=deploy）。
  - 同步模式：直接标记 `succeeded`。
  - 异步模式：
    - 可执行 Scrapyd `addversion.json`（上传 egg）。
    - 自动注册/更新 source_library 的 channel/item 绑定（`provider_type=scrapy`）。
  - 项目状态从 `imported/deploy_queued` 到 `deployed/deploy_failed`。

### 1.3 Rollback（回滚）
- API：`POST /crawler/projects/{project_key}/rollback`
- 入口：`main/backend/app/api/crawler.py#rollback_crawler_project_api`
- 核心服务：`main/backend/app/services/crawlers_mgmt/service.py#rollback_project`
- 编排任务：`task_orchestrate_crawler_rollback`
- 当前行为：
  - 创建 `public.crawler_deploy_runs` 记录（action=rollback）。
  - 可调用 Scrapyd `delversion.json` 删除版本。
  - 可将 source_library 对应 channel 的 `provider_type` 切回 `native`（灰度/回退）。
  - 项目状态更新为 `rolled_back/rollback_failed`。

### 1.4 Run-item（信息源项执行）
- API：`POST /source_library/items/{item_key}/run`
- 入口：`main/backend/app/api/source_library.py#run_item`
- 核心服务：
  - `run_item_by_key`：`main/backend/app/services/source_library/resolver.py`
  - `run_channel`：`main/backend/app/services/source_library/runner.py`
- 当前行为：
  - 合并参数：`channel.default_params + item.params + ingest_config + override_params`。
  - provider_type 命中 `scrapy/crawlee/meltano` 时，走 crawler provider registry。
  - 由 `execution_policy` 控制灰度 allowlist（project/item 级）。
  - `scrapy` 可自动 ingest 输出，写回 inserted/updated/skipped/errors。

---

## 2) 开源替代参考池（3-5个）

## A. Scrapyd + Spidermon + SpiderKeeper（Scrapy Cloud 类替代，优先）
- 定位：最贴近当前架构（Scrapy 项目版本部署 + 任务调度 + 监控告警 + Web 管理）。
- 适配点：
  - 直接替换当前 Scrapyd 单点，补齐监控与管理层。
  - 保留现有 `crawler_deploy_runs` 与 source_library 注册逻辑。
- 官方链接：
  - Scrapyd: https://scrapyd.readthedocs.io/
  - Spidermon: https://spidermon.readthedocs.io/
  - SpiderKeeper: https://github.com/DormyMo/SpiderKeeper

## B. Airbyte OSS
- 定位：以连接器为核心的数据采集平台；适合把 source_library item 抽象为 connector/job。
- 适配点：
  - 用 Connector + Connection 替代部分 channel/item 组合。
  - 利用标准化调度、状态管理、失败重试、目的端落地能力。
- 官方链接：
  - https://docs.airbyte.com/
  - https://github.com/airbytehq/airbyte

## C. Meltano（含 Singer 生态）
- 定位：ELT 编排与插件化运行时，适合将 source_library 变为“可版本化的数据管道项目”。
- 适配点：
  - 将 item 视作 job/pipeline 任务单元，支持环境配置、调度、CI 友好。
  - 与现有 `provider_type=meltano` 语义天然一致。
- 官方链接：
  - https://docs.meltano.com/
  - https://github.com/meltano/meltano

## D. Apache Airflow
- 定位：通用工作流编排；适合统一 deploy/run/rollback 审计与重试策略。
- 适配点：
  - 将 import/deploy/rollback/run-item 编排成 DAG。
  - 用 task instance + metadata DB 提供统一 run 视图。
- 官方链接：
  - https://airflow.apache.org/docs/
  - https://github.com/apache/airflow

## E. Dagster OSS
- 定位：资产（asset）与 lineage 优先的数据编排框架，适合产物模型治理。
- 适配点：
  - 将 crawler 输出抽象成 asset，天然支持 lineage 与可观测性。
  - 便于将 source_library item 运行结果沉淀为可追踪资产版本。
- 官方链接：
  - https://docs.dagster.io/
  - https://github.com/dagster-io/dagster

---

## 3) 任务模型与产物模型映射（artifact / run / lineage）

| 维度 | 当前系统（代码现状） | Scrapyd+Spidermon+SpiderKeeper | Airbyte | Meltano | Airflow/Dagster |
|---|---|---|---|---|---|
| Artifact | `crawler_projects.current_version/deployed_version` + egg + source_library channel/item 配置 | Scrapyd project version + SpiderKeeper 项目配置 | Connector/Connection 配置版本、catalog/state | `meltano.yml` + plugin lock + env | DAG/asset 定义与版本（代码仓） |
| Run | `crawler_deploy_runs`（deploy/rollback）+ source item 执行返回 | Scrapyd job + Spidermon 监控事件 | Job/Sync Run | Job run / schedule run | Task run / run record |
| Lineage | 现状偏弱；依赖 `analysis_plan`、run 记录和日志串联 | 通过 job + monitor 事件构建弱 lineage | source->destination lineage（连接级） | tap->target 流向 + logs | DAG 依赖/asset graph 天然 lineage |

建议的统一映射（可落地于本仓库的抽象层）：
- `artifact_id`: `<platform>:<project_or_connector>:<version>`
- `run_id`: `<platform>:<job_or_run_id>`
- `lineage_edge`:
  - `artifact -> run`（由哪个版本触发）
  - `run -> dataset/document`（产出哪些数据）
  - `source_library_item -> artifact`（业务入口绑定到平台工件）

---

## 4) PoC 命令（本地可演示）

前提：本地 Docker 可用；以下命令为最小演示，验证“可跑通 + 可观察”。

### 4.1 Scrapyd 最小 PoC
```bash
docker run -d --name poc-scrapyd -p 6800:6800 scrapinghub/scrapyd
curl -s http://127.0.0.1:6800/daemonstatus.json
# 预期：返回 status=ok 与 pending/running/finished 计数
```

### 4.2 Airbyte OSS 最小 PoC
```bash
mkdir -p /tmp/poc-airbyte && cd /tmp/poc-airbyte
curl -LsfS https://raw.githubusercontent.com/airbytehq/airbyte/master/run-ab-platform.sh -o run-ab-platform.sh
chmod +x run-ab-platform.sh
./run-ab-platform.sh -b
# 预期：本地 Airbyte 服务启动，可访问 Web UI
```

### 4.3 Meltano 最小 PoC
```bash
python -m venv .venv && source .venv/bin/activate
pip install -U meltano
meltano init poc_meltano && cd poc_meltano
meltano --version
# 预期：输出 meltano 版本并完成项目初始化
```

### 4.4 对接当前后端 API 的最小演示
```bash
# 1) 导入 crawler 项目
curl -X POST http://127.0.0.1:8000/crawler/projects/import \
  -H 'Content-Type: application/json' \
  -d '{"project_key":"poc_chain4","name":"poc_chain4","provider":"scrapyd","source_type":"git","source_uri":"https://example.com/repo.git"}'

# 2) 异步 deploy（触发编排）
curl -X POST http://127.0.0.1:8000/crawler/projects/poc_chain4/deploy \
  -H 'Content-Type: application/json' \
  -d '{"async_mode":true}'

# 3) 运行 source library item
curl -X POST http://127.0.0.1:8000/source_library/items/crawler.poc_chain4.default/run \
  -H 'Content-Type: application/json' \
  -d '{"project_key":"poc_chain4","async_mode":false,"override_params":{}}'
```

---

## 5) 风险与回滚

## 5.1 主要风险
- 平台碎片化风险：Scrapy/Airbyte/Meltano 多栈并行会造成 run 视图割裂。
- 状态一致性风险：当前 `crawler_deploy_runs` 与外部平台 run_id 尚无强一致约束。
- 产物一致性风险：artifact 版本策略不统一（egg 版本、connector 版本、pipeline 版本）。
- 灰度误配置风险：`execution_policy.allowlist` 配置错误可能导致误切流。

## 5.2 回滚策略（建议）
- L1（执行层回滚）：失败 run 自动重试，超过阈值后停止并报警。
- L2（路由层回滚）：将 channel `provider_type` 从 `scrapy/meltano/crawlee` 切回 `native`（现有能力已支持）。
- L3（版本层回滚）：deploy 版本回退到 `previous_version`，并记录 `crawler_deploy_runs(action=rollback)`。
- L4（平台层回滚）：保留双写/镜像期，逐项目切换；任一平台异常可整批回切到当前原生链路。

## 5.3 最小落地顺序
1. 先做 Scrapyd + Spidermon + SpiderKeeper（最小改动、最大兼容）。
2. 再选 Airbyte 或 Meltano 之一做 source_library 分层替换（建议先 Meltano，因现有 provider_type 已预留）。
3. 最后引入 Airflow/Dagster 做统一 run+lineage 平台层。
