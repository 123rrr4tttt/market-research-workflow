# 市场情报（market-intel）信息流优化路线（A -> C）

> 最后更新：2026-02

本目录用于管理“市场情报工作流”的通用商业信息流优化实施，按最小改造优先，逐步演进到平台化能力。

## 1. 总体目标

- 用最少改动先提升抓取稳定性、正文质量、去重能力。
- 保持现有主干：`FastAPI + Celery + SQLAlchemy + PostgreSQL + Redis + Elasticsearch`。
- 兼容现有 `project schema` 隔离与 `aggregator` 汇总架构。

## 2. A 到 C 实施计划

## A 阶段（1-2 周，最小改造）

### 目标
- 不改核心架构，先解决“抓取质量和稳定性”。

### 组件
- `httpx`（替换现有同步 HTTP 调用）
- `trafilatura`（统一正文提取）
- Redis URL 去重（`SET NX` 或 Bloom）
- `feedparser`（补 RSS 采集能力）

### 关键动作
1. 替换 `http_utils` 的 HTTP 客户端为 `httpx`，保留接口不变。
2. 在新闻/政策类 adapter 引入 `trafilatura.extract()`。
3. 入库前加 URL 去重（先用 Redis `SET NX`，后续可升级 Bloom）。
4. 新增 `RssNewsAdapter`，覆盖 3-5 个稳定行业源。

### 预期产出
- 抓取成功率提升。
- 正文提取质量提升。
- 重复文档明显下降。

---

## B 阶段（2-4 周，中等改造，质量优先）

### 目标
- 增强“动态页面采集”和“内容级去重”。

### 组件
- A 阶段全部
- `simhash-py`（正文近重复检测）
- `scrapy-playwright`（针对 JS 动态页）
- `PRAW`（Reddit 合规采集）

### 关键动作
1. 对新闻/政策正文计算 SimHash，写入前做近重复拦截。
2. 抽 1-2 个高难页面 adapter，接入 `scrapy-playwright`。
3. 社媒层优先采用 `PRAW`，减少非官方接口不稳定性。
4. 建立 A/B 对比：旧 adapter 与新 adapter 并跑一个周期。

### 预期产出
- 内容重复率进一步下降。
- 动态页抓取成功率可控。
- 社媒数据稳定性和合规性提升。

---

## C 阶段（4-8 周，长期平台化）

### 目标
- 形成可扩展的标准化采集平台，支持多项目并行增长。

### 组件
- B 阶段全部
- `Scrapy + scrapy-redis`（分布式调度）
- Bloom 去重体系（统一 URL 层）
- 统一可观测（结构化日志 + 指标）

### 关键动作
1. 将高价值 HTML adapter 逐步迁移为 Scrapy Spider。
2. 引入 `scrapy-redis` 做分布式队列与调度。
3. 统一抓取指标、错误分类、延迟监控。
4. 建立“采集模板”：Topic 配置驱动 adapter 组合。

### 预期产出
- 高并发与多源采集能力提升。
- 采集链路可观测、可回放、可排障。
- 更容易扩展新 Topic 与新市场。

---

## 3. 预期收集层架构（目标分层）

按“最少侵入现有代码”的方式，建议采用以下层级：

1. **API 编排层（FastAPI）**
   - 接收 Topic/project 请求，触发 ingest 任务。
   - 只做参数校验与任务编排，不做重逻辑。

2. **任务调度层（Celery）**
   - 负责异步执行与重试。
   - 每个任务绑定 `project_key`，确保 schema 隔离正确。

3. **Adapter 抽象层（Source-specific）**
   - 每个来源一个 adapter，输出统一 DTO。
   - 支持官方 API、RSS、HTML、JS 页面四类来源。

4. **HTTP/抓取执行层**
   - 默认 `httpx`；必要时切 `playwright` 下载器。
   - 统一超时、重试、代理、UA 策略。

5. **解析与抽取层**
   - 结构化字段解析（标题、日期、来源、正文）。
   - 正文优先 `trafilatura`，再进入 LLM/规则抽取。

6. **去重与增量层**
   - URL 去重（Redis）。
   - 内容去重（SimHash）。
   - 增量游标按 source/topic/project 维护。

7. **存储与索引层**
   - 项目库：按 schema 写入业务表。
   - 总库：aggregator 异步汇总。
   - 检索：ES 保留 `project_key/topic/domain` 维度。

8. **观测与治理层**
   - 指标：成功率、延迟、去重率、异常率。
   - 治理：TTL、归档、项目级清理。

---

## 4. 阶段验收建议

- A：重点看抓取成功率、正文可读性、URL 重复率。
- B：重点看内容重复率、动态页成功率、社媒稳定性。
- C：重点看扩展速度、任务稳定性、运维可观测性。

建议每阶段结束保留一次“对比报告”（改造前后 KPI）。
