# Ingest Platformization Assessment and Roadmap (2026-03-02)

## 1. Goal

对当前信息采集链条进行平台化评估，并形成可执行的最小落地路线，覆盖：

- 后端能力平台化
- API/前端接入平台化
- 质量治理平台化
- 运营可观测平台化

平台化边界约束（本轮决策）：

- `single_url` 作为平台化唯一入库工作流（single write workflow）。
- `url_pool`、`source_library`、`discovery`、`raw_import` 等仅作为候选生产或任务编排层，不再定义独立入库语义。

## 2. Overall Conclusion

结论：当前链条已达到 **Platform-ready（可平台化）**，但尚未达到 **Production Platform（可规模化运营）**。

成熟度分级（内部建议）：

- L2.5 / 5
- 能力骨架已成，运营闭环未成

## 3. Evidence by Dimension

### 3.1 Backend Architecture

已具备：

- `single_url` 统一输入输出契约，返回 `status/inserted/inserted_valid/rejected_count/rejection_breakdown/degradation_flags`
- `search_template + fallback + fanout + crawler_pool` 的主分支已形成可复用编排
- URL/content/provenance 三层 gate 已接入同一主链路

主要不足：

- `single_url` 职责较重，路由、抓取、解析、规则、持久化耦合在单文件
- 规则常量硬编码较多，不利于租户化策略治理

### 3.2 API and Frontend Integration

已具备：

- `/api/v1/ingest/url/single` 参数可外部化传入（search expand/fallback/filter 等）
- 任务链路支持同步/异步透传 `search_options`

主要不足：

- 前端 `ingestSingleUrl` 客户端可用，但业务入口和运营表单联动仍需补齐
- 默认值省略传递策略，存在行为漂移风险

### 3.3 Quality and Dirty-Data Governance

已具备：

- 在线拦截闭环：`url_policy_check` + `content_quality_check` + `provenance gate`
- 历史清理闭环：`cleanup_meaningless_docs.py` 与在线脏页类型对齐
- 已纳入并验证中间页治理：GitHub 中间页、DDG 中间页、乱码脚本壳页

主要不足：

- 并非所有写入入口都共享同一 GateService（存在策略漂移）
- 在线与离线规则演进仍可能不同步

### 3.4 Ops and Observability

已具备：

- 有任务历史、日志、状态、降级标识，支持基础排障
- 过程页可查看关键执行结果

主要不足：

- 缺统一 `error_code` 维度与聚合指标口径
- 缺按历史任务参数一键 replay 能力
- 缺任务级 SLO 看板（success/degraded/p95/retry）

## 4. Platformization Gaps (Priority)

P0:

1. 规则中心化：所有入口统一回流 `single_url` 并复用同一规则源
2. `single_url` 分阶段 pipeline 化：`classify -> fetch -> parse -> gate -> persist`

P1:

1. 前端入口闭环：补 single-url 表单与动作编排
2. 任务标准观测字段：`error_code/degradation_flags/quality_score`

P2:

1. 可回放：`POST /process/{job_id}/replay`
2. 误杀/漏杀回归基准集 + CI 对比

## 5. Two-Week Execution Board

### Week 1 - Core Platform Layer

Task A (P0): GateService consolidation

- 抽象统一 GateService（URL/content/provenance reason code）
- 改造入口统一调用，消除分支重复判断
- 输出标准拒绝码映射表（稳定对外契约）

Task B (P0): `single_url` pipeline refactor

- 拆分阶段函数与上下文对象
- 主函数仅负责 orchestration
- 保持返回字段兼容

Task C (P1): contract hardening

- 显式回传完整生效配置（含默认值）
- 异步调用改为 kwargs 语义（减少签名漂移）

### Week 2 - Productization and Ops

Task D (P1): frontend integration

- 在前端补 single-url 配置入口
- 对接关键 search/provenance 参数展示

Task E (P1): observability baseline

- 任务结果统一记录 `error_code` 与质量字段
- 提供 success/degraded/p95 的聚合接口

Task F (P2): replay and regression

- 新增 job replay API
- 建立误杀/漏杀样本集与自动回归

## 6. Acceptance Criteria

功能：

- 新中间页脏数据（GitHub/DDG/乱码壳）入库命中率显著下降并可解释
- 所有主要入口共享统一 gate reason code

契约：

- API/任务结果返回稳定，默认值语义显式可见
- 前端可透传并展示关键平台化参数与拒绝原因

运维：

- 可按日查看 success/degraded/p95
- 支持基于历史任务参数的一键 replay

## 7. Risks and Controls

风险：

- 规则收敛可能带来短期误杀
- pipeline 重构可能引入分支回归

控制：

- 先在 `demo_proj` 灰度
- 保持 reason code 稳定并对比回归样本
- 提供 feature flag 快速回滚

