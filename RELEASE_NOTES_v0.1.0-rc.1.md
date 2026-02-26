# 预发行版版本说明（v0.1.0-rc.1）

- 版本类型：`预发行版（Release Candidate）`
- 版本号：`v0.1.0-rc.1`
- 日期：`2026-02-26`

## 1. 本次版本定位

本版本是 `v0.1.0` 的预发行候选版本，目标是验证“资源池（resource pool）主链路 + 统一搜索 + 采集运行时整合”的可用性与稳定性，为后续正式版发布提供验证基础。

适用场景：

- 内部联调
- 功能验收
- 迁移脚本验证
- 前端管理台联动测试

暂不建议直接作为生产稳定版本长期运行。

## 2. 主要变更（按模块）

### 2.1 资源池（Resource Pool）能力增强

- 新增资源池相关 API（`main/backend/app/api/resource_pool.py`）
- 新增资源池服务模块（`main/backend/app/services/resource_pool/`）
- 增强站点条目（site entries）、抽取、解析、校验、自动分类等能力
- 补充统一搜索链路（含候选 URL 处理与工具函数）

### 2.2 采集运行时（Collect Runtime）引入

- 新增采集运行时模块（`main/backend/app/services/collect_runtime/`）
- 新增多类运行时 adapter（搜索、来源库、URL 池等）
- 补充运行时契约与展示元数据支持，便于后续流程平台化和可视化

### 2.3 来源库（Source Library）扩展

- 扩展来源库 adapter 体系（`main/backend/app/services/source_library/adapters/`）
- 新增 `handler_registry`、`url_router` 等基础设施
- 优化来源解析/执行链路（resolver / runner）

### 2.4 采集与发现链路联动优化

- 调整 `discovery`、`ingest`、`process`、`tasks` 等相关接口与服务
- 强化关键字生成、Web 搜索与文档链路衔接
- 支持资源池/来源库与采集流程的贯通

### 2.5 数据库迁移（重要）

新增资源池相关迁移脚本（按当前工作区文件）：

- `main/backend/migrations/versions/20260226_000001_add_resource_pool_tables.py`
- `main/backend/migrations/versions/20260226_000002_add_resource_pool_capture_config.py`
- `main/backend/migrations/versions/20260226_000003_add_ingest_config.py`
- `main/backend/migrations/versions/20260226_000004_add_resource_pool_site_entries.py`

### 2.6 前端与文档

- 新增资源池管理页模板（`main/frontend/templates/resource-pool-management.html`）
- 更新若干页面模板与流程管理页面
- 新增/更新资源库、统一搜索、采集运行时相关设计与验证文档

## 3. 兼容性与升级提示

### 3.1 API / 前端

- 部分 API 路由与前端模板有联动改动，升级时建议前后端代码同步部署。
- 若仅升级后端、不升级模板，可能出现管理页入口或交互不一致。

### 3.2 数据库

- 本版本包含多条迁移脚本，升级前请先备份数据库。
- 建议在测试环境完整执行迁移并验证资源池主链路后，再推进到正式环境。

### 3.3 配置与运行时

- 新增来源库/采集运行时适配能力后，建议检查项目级配置、默认项目绑定与任务调度配置是否符合预期。

## 4. 验证重点（RC 阶段建议）

- 资源池条目创建、解析、分类、检索链路是否可闭环
- 统一搜索结果写回资源池/URL 池的正确性
- 迁移脚本执行顺序与幂等性（至少在测试环境验证一次）
- 前端资源池管理页面与后端 API 对接是否正常
- Celery 任务链在新增配置下是否稳定运行

## 5. 已知风险（预发行版）

- 模块新增较多（资源池、采集运行时、来源库 adapter），边界条件覆盖可能不足
- 迁移脚本与服务逻辑联动较多，环境差异可能暴露兼容性问题
- 前端模板和后端接口仍可能存在细节不一致，需要联调确认

## 6. 正式版发布建议（v0.1.0）

满足以下条件后再发布正式版：

- 关键迁移脚本在测试环境验证通过
- 资源池主链路（发现 → 写回 → 抓取/入库）稳定
- 前后端联调通过并完成至少一轮回归
- 补齐核心链路最小化测试/验收脚本结果记录

## 7. 建议打标方式

当前建议先打预发行标签：

```bash
git tag -a v0.1.0-rc.1 -m "release candidate: resource pool + unified search + collect runtime"
git push origin v0.1.0-rc.1
```

待验证通过后发布正式版：

```bash
git tag -a v0.1.0 -m "resource pool baseline stable release"
git push origin v0.1.0
```
