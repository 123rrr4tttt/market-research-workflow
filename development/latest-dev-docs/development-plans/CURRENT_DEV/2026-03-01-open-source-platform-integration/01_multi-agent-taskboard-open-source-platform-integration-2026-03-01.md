# 开源来源平台融合：多 Agent 并行开发任务书

- 日期：2026-03-01（US/Pacific）
- 来源文档：`F_PLAN/13_open-source-source-platform-integration-plan-2026-03-01.md`
- 目标：把来源扩展平台化能力拆成高并行、低耦合、可回滚的原子任务

## 1. 并行开发框架

角色：
- `Coordinator`：冻结契约、依赖编排、合并顺序控制
- `Worker-SL`：`source_library`
- `Worker-CR`：`collect_runtime`
- `Worker-CW`：`crawlers/scrapy_bridge`
- `Worker-TSK`：`tasks` 调度桥
- `Worker-PRC`：`process` 状态与日志
- `Worker-OPS`：`docker-compose` / 脚本
- `Worker-TST`：单测/集成/契约回归

边界规则：
- 每个 Worker 仅修改自己 ownership 文件
- PR 颗粒度保持 1-3 文件为主
- 不允许跨域顺手改动

## 2. 原子任务清单（含依赖）

| ID | Owner | 任务 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|---|
| T00 | Coordinator | 冻结统一契约：`provider_type/provider_config/execution_policy`、`CollectResult` 扩展字段 | F_PLAN/13 | 契约文档 + 字段清单 | 无 |
| T01 | Worker-CW | 新建 `services/crawlers/providers/base.py` | T00 | provider 抽象接口 | T00 |
| T02 | Worker-CW | 新建 `services/crawlers/providers/registry.py` | T01 | provider 注册器 | T01 |
| T03 | Worker-CW | 新建 `services/crawlers/providers/scrapy_provider.py`（先 mock） | T02 | scrapy provider 初版 | T02 |
| T04 | Worker-CW | 新建 `services/crawlers/scrapy_bridge/scrapyd_client.py` | T00 | scrapyd client + DTO | T00 |
| T05 | Worker-CR | 新建 `collect_runtime/adapters/crawler_scrapy.py` | T00 | crawler adapter | T00 |
| T06 | Worker-CR | 在 `collect_runtime/runtime.py` 注册 `crawler.scrapy` | T05 | 新 channel 可运行 | T05 |
| T07 | Worker-CR | 扩展 `CollectResult` 字段：`provider_job_id/provider_type/provider_status/attempt_count` | T00 | 统一结果契约升级 | T00 |
| T08 | Worker-CR | `display_meta` 兼容扩展字段 | T07 | process/前端可见新信息 | T07 |
| T09 | Worker-SL | `source_library/runner.py` 增加 provider registry 路由 | T02 | source_library -> provider 路由生效 | T02 |
| T10 | Worker-SL | `source_library/resolver.py` 透传 provider 元数据与执行策略 | T00 | item/channel 运行参数链完整 | T00 |
| T11 | Worker-SL | `source_library/types.py` 对齐新增字段 | T00 | 类型契约一致 | T00 |
| T12 | Worker-TSK | `tasks.py` 增加 `task_submit_crawler_job` | T04 | 提交外部抓取任务 | T04 |
| T13 | Worker-TSK | `tasks.py` 增加 `task_poll_crawler_job` | T12 | 轮询与状态归档 | T12 |
| T14 | Worker-PRC | 扩展 `EtlJobRun` 字段 + migration：`external_job_id/external_provider/retry_count` | T00 | 状态追踪模型升级 | T00 |
| T15 | Worker-TSK | `job_logger` 写入/更新外部 job 字段 | T14 | runtime 与 DB 状态一致 | T14 |
| T16 | Worker-PRC | `api/process.py` 按 provider 查询状态/日志 | T14 | celery + scrapyd 双栈可观测 | T14 |
| T17 | Worker-OPS | `docker-compose.yml` 新增 `scrapyd`（profile 可控） | T00 | ops 启动面可用 | T00 |
| T18 | Worker-OPS | `scripts/docker-deploy.sh` preflight 增强 scrapyd 检查 | T17 | 部署前校验可覆盖 scrapyd | T17 |
| T19 | Worker-OPS | `ops/start-all.sh`/`test-docker-startup.sh` 纳入 scrapyd | T17 | 本地与CI启动验证可用 | T17 |
| T20 | Worker-TST | 单测：provider registry 路由 | T02,T09 | registry 行为稳定 | T02,T09 |
| T21 | Worker-TST | 单测：CollectResult 映射与 runtime 聚合 | T07,T06 | 结果契约无回归 | T07,T06 |
| T22 | Worker-TST | 集成：source_library item -> crawler.scrapy -> CollectResult | T09,T06,T12 | 闭环验收通过 | T09,T06,T12 |
| T23 | Worker-TST | 契约：process list/stats/history 一致性 | T16 | 状态语义一致 | T16 |
| T24 | Coordinator | 文档与灰度开关：白名单来源启用 scrapy，保留 native 回退 | T17,T22,T23 | 可灰度上线与回滚 | T17,T22,T23 |

## 3. 并行波次（无依赖优先最大并行）

- Wave-0（并行度 1）：`T00`
- Wave-1（并行度 6）：`T01 T04 T05 T07 T10 T17`
- Wave-2（并行度 7）：`T02 T06 T08 T11 T14 T18 T19`
- Wave-3（并行度 6）：`T03 T09 T12 T16 T20 T21`
- Wave-4（并行度 4）：`T13 T15 T22 T23`
- Wave-5（并行度 1）：`T24`

## 4. 合并与验收门禁

每个 Wave 合并前必须通过：
1. 单元测试：`./scripts/test-standardize.sh unit`
2. 集成测试（涉及链路时）：`./scripts/test-standardize.sh integration`
3. 契约测试（API 变更时）：`./scripts/test-standardize.sh contract`
4. Docker 验证（ops 变更时）：`./scripts/test-standardize.sh docker`

## 5. 回滚策略（任务级）

- 路由开关：`provider_type=scrapy` 仅对白名单 item 生效
- 异常快速回退：单条来源回切 `provider_type=native`
- 保留旧 channel 与 native handler，不做破坏性删除

## 6. 当前执行建议（开工顺序）

1. 先并行做 `T01/T04/T05/T07/T10/T17`
2. 紧接 `T02/T06/T14`
3. 再推进 `T09/T12/T16` 与测试 `T20/T21`
4. 最后 `T13/T15/T22/T23`，完成后做 `T24` 灰度发布

## 7. 2026-03-01 当日落实状态（多 Agent 原子并行）

本轮按“爬虫管理独立页面 + 自动接入/部署编排”目标落地，状态如下：

- [x] A01 新增后端爬虫管理 API 路由：`/api/v1/crawler/*`
- [x] A02 新增爬虫项目与部署运行表模型：`CrawlerProject` / `CrawlerDeployRun`
- [x] A03 新增对应 migration：`20260301_000003_add_crawler_management_tables.py`
- [x] A04 新增爬虫管理 service（导入/列表/详情/部署/回滚/运行查询）
- [x] A05 新增 Scrapyd 编排层（addversion/delversion + source_library 自动注册）
- [x] A06 新增 Celery 原子任务（deploy/register/orchestrate/rollback/provider-toggle）
- [x] A07 前端新增独立页面 `CrawlerManagePage`（与信息资源管理拆分）
- [x] A08 前端导航接入新页面入口 `crawler-management.html`
- [x] A09 前端 API 契约补齐（crawler endpoints/types/services）
- [x] A10 关键契约修复：后端按 `project_key` 路由，前后端 deploy/rollback 响应对齐
- [x] A11 支持“仅 URL 导入”的最小自动化路径（无 egg 时 registration-only）
- [x] A12 新增/补充测试文件（bridge / contract）

### 7.1 原子任务产出文件（本轮）

- `main/backend/app/api/crawler.py`
- `main/backend/app/services/crawlers_mgmt/service.py`
- `main/backend/app/services/crawlers_mgmt/orchestration.py`
- `main/backend/app/services/crawlers_mgmt/__init__.py`
- `main/backend/app/services/tasks.py`
- `main/backend/app/models/entities.py`
- `main/backend/migrations/versions/20260301_000003_add_crawler_management_tables.py`
- `main/frontend-modern/src/pages/CrawlerManagePage.tsx`
- `main/frontend-modern/src/app/shell/AppShell.tsx`
- `main/frontend-modern/src/app/navigation/index.ts`
- `main/frontend-modern/src/lib/api/endpoints.ts`
- `main/frontend-modern/src/lib/api/services/crawlers.ts`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/types.ts`

### 7.2 验收记录

1. 前端构建：`npm run build` 通过（`main/frontend-modern`）。
2. 后端语法检查：`python3 -m py_compile` 通过（变更文件）。
3. 后端新增测试：`python3 -m pytest` 执行结果为 `skip`（当前环境缺少完整依赖）。
4. 后端应用启动验证未完成：当前环境缺少 `fastapi` 运行依赖。
