# 开源来源平台融合开发文档（本地优先）

- 最后更新：2026-03-01（US/Pacific）
- 目标范围：先做“来源扩展平台化”，后续再接时间维度
- 当前阶段：执行方案（可直接进入开发）

## 1. 文档目标

1. 明确要融合的开源项目与角色定位。
2. 给出你现有仓库的文件级改造方案。
3. 定义分阶段里程碑、验收标准、回滚策略。
4. 保证“低侵入接入”，不推翻现有 `FastAPI + Celery + ES + pgvector` 主链路。

## 2. 选型结论（只选开源）

1. 第一层（必须）：`Scrapy + Scrapyd`
2. 第二层（可选增强）：`Crawlee for Python`
3. 第三层（API 来源标准化）：`Meltano + Singer`

官方仓库：
- Scrapy: `https://github.com/scrapy/scrapy`
- Scrapyd: `https://github.com/scrapy/scrapyd`
- Crawlee Python: `https://github.com/apify/crawlee-python`
- Meltano: `https://github.com/meltano/meltano`
- Singer Getting Started: `https://github.com/singer-io/getting-started`

## 3. 架构定位（与你现有代码映射）

1. 你现有主控制层保持不变：`main/backend/app/api/*`、`main/backend/app/services/tasks.py`
2. `source_library` 继续做“来源配置与路由中枢”：`main/backend/app/services/source_library/*`
3. `collect_runtime` 继续做“统一执行入口”：`main/backend/app/services/collect_runtime/*`
4. 新增“开源执行桥接层”：
- `scrapy_bridge`：管理 spider 任务提交、状态查询、结果回收
- `crawler_provider_registry`：将来源条目映射到 scrapy/crawlee/meltano provider

## 4. 融合边界（硬规则）

1. 来源配置仍由 `source_library` 管理，不把业务配置散落到爬虫项目内部。
2. 开源框架只负责“抓取执行”，入库与业务规则仍在你后端服务侧统一处理。
3. 所有执行结果都回流成统一 `CollectResult` 结构。
4. 不在本阶段新增时间事实模型；只保留必要运行时间戳用于任务观测。

## 5. 开发阶段计划

## Phase A（第1-2周）：Scrapy 基础融合

目标：实现“来源条目 -> Scrapy spider -> 结果回流 -> 入库”闭环。

任务：
1. 新建目录 `main/backend/app/services/crawlers/scrapy_bridge/`
2. 新增 provider 接口与注册器：
- `main/backend/app/services/crawlers/providers/base.py`
- `main/backend/app/services/crawlers/providers/registry.py`
3. 增加 `scrapy` provider 适配：
- `main/backend/app/services/crawlers/providers/scrapy_provider.py`
4. 在 `collect_runtime` 增加新 channel（例如 `crawler.scrapy`）：
- 更新 `main/backend/app/services/collect_runtime/runtime.py`
- 新增 `main/backend/app/services/collect_runtime/adapters/crawler_scrapy.py`
5. 将 `source_library` 条目可映射到 crawler provider：
- 更新 `main/backend/app/services/source_library/runner.py`
- 更新 `main/backend/app/services/source_library/resolver.py`

验收：
1. 新增一个来源条目可触发 Scrapy 抓取。
2. 结果可回流为统一 `CollectResult`，并完成文档入库。
3. 失败路径可返回标准错误信息，不影响现有 channel。

## Phase B（第3周）：Scrapyd 服务化调度

目标：将 Scrapy 执行从本进程调用升级为独立服务调度。

任务：
1. 在 `main/ops/docker-compose.yml` 增加 `scrapyd` 服务（profile 可控）。
2. 新增 Scrapyd 客户端：
- `main/backend/app/services/crawlers/scrapy_bridge/scrapyd_client.py`
3. 扩展 Celery 任务桥接：
- 更新 `main/backend/app/services/tasks.py`
- 增加 `task_submit_crawler_job` 与 `task_poll_crawler_job`
4. 结果归档：
- 统一记录到 `EtlJobRun` 与 process API 可见状态。

验收：
1. 通过 API 提交来源任务后，可看到 scrapyd job id。
2. `process` 端点可查询执行状态并关联日志。
3. 任务失败重试策略可配置并生效。

## Phase C（第4周）：Crawlee 动态站点增强（可选）

目标：为 JS 渲染和复杂反爬站点提供稳定抓取路径。

任务：
1. 新增 Crawlee provider：
- `main/backend/app/services/crawlers/providers/crawlee_provider.py`
2. 将 `source_library` 中占位 channel 落地：
- `special_web.js_render`
- `special_web.anti_bot`
3. 对特定来源条目开启 provider 路由策略（按域名或 channel）。

验收：
1. 至少 1 个动态站点来源可稳定抓取并回流。
2. 与 Scrapy provider 可并存，切换由配置驱动。

## Phase D（第5-6周）：Meltano/Singer API 来源规范化（可选）

目标：把 API 类来源改为标准 connector 管理模式。

任务：
1. 新增 Meltano provider：
- `main/backend/app/services/crawlers/providers/meltano_provider.py`
2. 统一 state 处理：cursor/bookmark 写回。
3. 对现有 API 源（例如部分 market/policy API）做 1-2 个试点迁移。

验收：
1. API 来源可增量同步，不重复全量抓取。
2. 失败恢复后可以从上次状态继续。

## 6. 代码改造清单（第一批必须改）

1. 调度与执行
- `main/backend/app/services/tasks.py`
- `main/backend/app/celery_app.py`
- `main/backend/app/api/process.py`

2. 来源平台
- `main/backend/app/services/source_library/runner.py`
- `main/backend/app/services/source_library/resolver.py`
- `main/backend/app/services/source_library/types.py`

3. 统一运行时
- `main/backend/app/services/collect_runtime/runtime.py`
- `main/backend/app/services/collect_runtime/contracts.py`
- `main/backend/app/services/collect_runtime/adapters/`（新增 crawler adapter）

4. 新增模块
- `main/backend/app/services/crawlers/`（全新）

5. 运维配置
- `main/ops/docker-compose.yml`
- `scripts/docker-deploy.sh`
- `main/ops/README.md`

## 7. 数据与契约设计

1. `source_library` 条目新增建议字段：
- `provider_type`（`native/scrapy/crawlee/meltano`）
- `provider_config`（JSON）
- `execution_policy`（重试、超时、并发）

2. `CollectResult` 统一扩展字段：
- `provider_job_id`
- `provider_type`
- `provider_status`
- `attempt_count`

3. `EtlJobRun` 建议扩展：
- `external_job_id`
- `external_provider`
- `retry_count`

## 8. 测试策略

1. 单元测试
- provider registry 路由正确性
- provider config schema 校验
- CollectResult 映射一致性

2. 集成测试
- source_library item -> crawler provider -> 入库闭环
- 失败重试与错误语义
- process API 任务状态查询一致性

3. 回归测试
- 保证 `search.market/search.policy/source_library/url_pool` 现有路径不回归
- 保证 `project_key` 隔离与 header 观测不回归

## 9. 运行与发布

1. 发布顺序
- 先合并 provider registry 与 mock provider
- 再接入 scrapy provider
- 最后启用 scrapyd 服务化

2. 灰度策略
- 仅对白名单来源条目启用 `provider_type=scrapy`
- 出现异常可单条回退到 `native`

3. 回滚策略
- 保留旧 channel 实现
- provider 路由开关可即时切回
- 不做破坏性 schema 删除

## 10. 风险与控制

1. 风险：新增执行层导致任务复杂度上升。  
控制：统一 provider contract，所有 provider 输出同一结果模型。

2. 风险：Scrapyd 运维复杂。  
控制：先本地同进程验证，再上独立服务；保留 native 回退。

3. 风险：来源扩展快于治理。  
控制：先引入评分与状态机，再扩大来源数量。

4. 风险：测试不足导致线上不稳定。  
控制：先补齐关键链路自动化再扩大灰度范围。

## 11. 完成定义（DoD）

1. 新来源接入成本下降到“配置 + 轻量适配代码”。
2. 任务状态在 `process` 与 `EtlJobRun` 可追踪。
3. 至少 2 类来源（静态站点 + 动态站点）通过统一平台执行。
4. 不影响现有主链路稳定性与 project 隔离。
