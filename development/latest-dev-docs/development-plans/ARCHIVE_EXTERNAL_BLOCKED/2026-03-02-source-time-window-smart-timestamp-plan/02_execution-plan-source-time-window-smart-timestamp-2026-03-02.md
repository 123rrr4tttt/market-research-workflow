# Execution Plan: Source Time-Window + Smart Timestamp + Noun-Space Density (2026-03-02)

## 1. 目标与交付

本执行计划用于把方案文档落地为可运行能力，交付以下四项：

1. 文档级智能时间戳链路：`source_time -> effective_time`（回退 `ingested_at`）。
2. 每源时间窗统计与绘图接口：按 `effective_time` 统一过滤与聚合。
3. 名词向量组入库与聚合：支持 `source_domain × noun_group_id` 采集密度。
4. 质量看板：`source_time_coverage`、`density`、`norm_density`。

## 1.1 执行状态声明（2026-03-02）

- 本文档是实施计划，不代表功能已上线。
- 当前代码链路仍为原有流程；本计划定义后续改造步骤。
- 改造策略明确为：先“参数嵌入式接入”，再“模块化解耦重构”。

---

## 2. 执行边界

1. 本轮实现范围
- 后端字段、解析器、聚合 API、前端图表与筛选联动、历史回填任务。

2. 非目标
- 不改动搜索策略与绕过重复区调度策略。
- 不上线新的抓取 provider。

3. 架构策略
- 过渡阶段：新增字段/参数嵌入原流程，保证兼容与最小改动。
- 目标阶段：时间解析与名词密度计算独立模块化，主流程仅编排。

---

## 3. 里程碑（建议 6 个工作日）

1. `D1`：参数嵌入阶段设计冻结（Schema/API/字段口径）。
2. `D2`：嵌入式写入与查询能力落地（保持原流程兼容）。
3. `D3`：统计 API（每源 + 名词空间密度）完成。
4. `D4`：前端时间窗滑条 + 图表联调完成。
5. `D5`：模块化解耦重构（Resolver/Aggregator 抽离）。
6. `D6`：灰度验收、回归测试、发布准备。

---

## 4. 原子任务拆解（可并行）

### Track A: 时间语义主链（Backend）

Task A1: 字段迁移
- 目标：补齐文档级时间语义字段。
- 输入：现有 `documents` 表。
- 输出：新增字段与索引。
- 验收：迁移可重复执行，旧数据不损坏。

Task A2: Timestamp Resolver
- 目标：实现候选抽取、打分、回退、provenance 记录。
- 输入：页面元数据/正文候选/采集时间。
- 输出：`source_time/effective_time/time_confidence/time_provenance`。
- 验收：单元测试覆盖优先级、异常时间、时区归一。

Task A3: 写入链路接入
- 目标：所有单 URL 入库入口统一写入 `effective_time`。
- 输入：当前 ingest 持久化流程。
- 输出：写入字段稳定可查。
- 验收：入库后 API 返回字段完整。

### Track B: 名词空间密度（Backend）

Task B1: 名词抽取与向量组映射
- 目标：文档侧补 `noun_vector_group_ids`。
- 输入：正文文本。
- 输出：名词组 ID 列表与版本号。
- 验收：同义词汇归并稳定、版本可追踪。

Task B2: 聚合视图/查询
- 目标：实现 `source_domain × noun_group_id × time_bucket` 聚合。
- 输入：文档表 + 名词组映射。
- 输出：`effective_new_docs/density/norm_density`。
- 验收：统计结果与样本抽查一致。

Task B3: 统计 API
- 目标：提供每源趋势接口 + 名词空间密度接口。
- 输入：时间窗、bucket、source/noun 过滤参数。
- 输出：统一 envelope 的统计结果。
- 验收：契约测试通过，字段齐全。

### Track C: 前端可视化（Frontend）

Task C1: 时间窗控件
- 目标：预设 + 自定义时间窗滑条组件。
- 输入：UI 设计与 API 参数约定。
- 输出：`time_window/start/end` 联动状态。
- 验收：切换时间窗触发统一刷新。

Task C2: 每源时间窗图
- 目标：展示 `total_docs/source_time_coverage/fallback_ratio`。
- 输入：每源统计 API。
- 输出：折线或堆叠图。
- 验收：图表值与接口返回一致。

Task C3: 名词空间×域名热力图
- 目标：展示 `density/norm_density`。
- 输入：名词空间密度 API。
- 输出：热力图 + Tooltip。
- 验收：下钻跳转文档列表正确。

### Track D: 数据回填与验收（Ops/Data）

Task D1: 历史回填任务
- 目标：补齐历史文档时间语义与名词组字段。
- 输入：历史文档批次。
- 输出：幂等回填任务日志。
- 验收：失败可重试、可续跑。

Task D2: 质量报表
- 目标：产出源时间命中率与密度分布日报。
- 输入：聚合视图。
- 输出：`source_time_coverage`、`density`、`norm_density` 报表。
- 验收：报表口径与 API 一致。

---

## 5. API 契约冻结清单

1. 文档列表接口必须返回：
- `source_time`
- `ingested_at`
- `effective_time`
- `time_confidence`
- `time_provenance`
- `noun_vector_group_ids`

2. 每源时间窗接口必须返回：
- `source_domain`
- `bucket_time`
- `total_docs`
- `with_source_time_docs`
- `fallback_ingested_docs`
- `source_time_coverage`

3. 名词空间密度接口必须返回：
- `source_domain`
- `noun_group_id`
- `bucket_time`
- `effective_new_docs`
- `density`
- `norm_density`
- `dup_ratio`（可选）

---

## 6. 验收门禁（每阶段至少一个）

1. 单元门禁
- Resolver 时间优先级测试通过。
- 名词分组映射稳定性测试通过。

2. 集成门禁
- 指定关键词样本入库后可查询到 `effective_time` 与 `noun_vector_group_ids`。

3. 契约门禁
- 统计接口字段不缺失，类型符合约定。

4. 前端门禁
- 时间窗切换后图表与列表保持同口径（抽样比对 10 组）。

5. 数据门禁
- 回填后 `effective_time` 覆盖率达到 100%。
- `source_time_coverage` 可按源稳定输出。

---

## 7. 风险、阈值与回滚

1. 风险：源时间解析误命中导致排序异常。
- 阈值：异常时间比例 > 1% 触发告警。
- 回滚：临时强制 `effective_time = ingested_at`（feature flag）。

2. 风险：名词聚类漂移导致 norm_density 波动过大。
- 阈值：同一名词组日波动超过历史均值 3 倍触发复核。
- 回滚：冻结 `noun_extraction_version`，回退到上一版本映射。

3. 风险：聚合查询性能下降。
- 阈值：P95 > 1.5s 持续 30 分钟。
- 回滚：切换到物化视图或降低 bucket 粒度。

---

## 8. 发布步骤（灰度）

1. 在 `demo_proj` 开启 feature flag：
- `enable_effective_time=true`
- `enable_noun_space_density=true`

2. 灰度观察 24 小时：
- API 错误率
- 统计延迟
- 覆盖率与密度波动

3. 通过后扩展到默认项目，保留回滚开关 72 小时。

---

## 9. 最小命令清单（实施时参考）

1. 后端测试：
- `pytest main/backend/tests/unit -q`

2. 指定模块测试：
- `pytest main/backend/tests/unit/test_single_url_ingest_unittest.py -q`

3. 前端检查（按项目脚本）：
- `npm run lint`
- `npm test`

4. 本地健康检查：
- `curl -sS http://127.0.0.1:8000/api/v1/health`

---

## 10. 完成定义（DoD）

1. 文档、接口、图表统一使用 `effective_time`。
2. 名词空间×域名密度可查询、可绘图、可解释。
3. 历史数据回填完成且覆盖率报告可追溯。
4. 门禁测试通过，灰度观测无阻断风险。
