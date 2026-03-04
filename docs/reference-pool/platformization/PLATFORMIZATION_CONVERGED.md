# Platformization Converged Doc (Frozen v1)

更新时间：2026-03-04

目标：把当前 7 条链路文档收敛为一份“可执行唯一方案”，用于后续代码/IO 级重构立项与排期。

## 0. Frozen Decisions（最终口径）

1. Ingest/Workflow：`Temporal + Redpanda`，全自托管，一次性切换（接口转换 + API协议适配快速跑通后全量切换）。
2. Search/Index：`OpenSearch + Qdrant`，`OpenSearch` 主检索、`Qdrant` 仅向量召回；影子验证不超过 3 天后全量切换。
3. Multi-tenant/Config：`Keycloak + Casbin`，租户采用逻辑隔离（`tenant_id + policy`）；配置先 `.env`，后迁移 `SOPS + Git`。
4. Crawler/Source：`Scrapyd + SpiderKeeper + Spidermon`；执行模型为 `crawler + connector` 双引擎；connector 唯一选型 `Airbyte`。
5. Data Contracts/API：主标准 `OpenAPI + JSON Schema`；门禁 `Spectral + openapi-diff + Pact`；先非阻断 2 天后转 required。
6. Observability/Ops：`OpenTelemetry + Prometheus/Grafana + Loki/Tempo`；发布策略先蓝绿快切，后续再引入金丝雀。
7. Frontend：页面级绞杀，不引入微前端框架；接口层保持前端直连后端 API。
8. LLM Embedded：主路径走 API provider（多服务商静态绑定）+ LiteLLM；治理采用 Langfuse+Promptfoo+DeepEval+Guardrails；Agent 采用 LangGraph+Temporal；RAG 采用 Qdrant+OpenSearch+pgvector；本地层仅应急兜底并保留未来部署接口。

## 1. 平台化边界（先统一口径）

1. 默认自托管优先，不依赖 SaaS 托管能力。
2. 业务能力和平台能力解耦：业务模块通过适配层调用平台组件。
3. 状态真相源保持在本项目主库（任务状态、运行结果、审计记录）。
4. 迁移采用“影子读写 -> 小流量 A/B -> 切换 -> 回滚窗口”。
5. 每条链路必须定义：输入/输出契约、观测指标、回滚动作。

## 2. 7 条主链路收敛决策（唯一方案）

| 链路 | 当前主问题 | 已定方案 | 说明 |
|---|---|---|---|
| Ingest/Workflow | 任务编排分散、补偿与重放弱 | Temporal + Redpanda | 全自托管；一次性切换 |
| Search/Index | 检索与索引耦合、演进成本高 | OpenSearch + Qdrant | OpenSearch主检索，Qdrant向量召回 |
| Multi-tenant/Config | 租户上下文与配置写入耦合 | Keycloak + Casbin | 逻辑租户隔离；配置两阶段迁移 |
| Crawler/Source | crawler 生命周期管理分散 | Scrapyd + SpiderKeeper + Spidermon + Airbyte | crawler+connector 双引擎 |
| Data Contracts/API | 契约治理分散在代码与测试 | OpenAPI/JSON Schema + Spectral + openapi-diff + Pact | 非阻断2天后required |
| Observability/Ops | 可观测闭环不完整 | OTel + Prom/Grafana + Loki/Tempo | 发布先蓝绿快切 |
| Frontend | legacy+modern 并存治理成本高 | 页面级绞杀（无微前端框架） | 前端直连后端API |

## 3. 代码/IO 级统一改造模式

1. `Adapter First`：每条链路先加 `runtime adapter`（保留旧实现）。
2. `Dual Path`：同一输入走 old/new 两条路径，产出对比指标。
3. `Contract Gate`：请求/响应/事件 schema 先落门禁再切流量。
4. `Observability First`：切换前先有指标、日志、trace 与报警。
5. `Rollback by Switch`：通过配置开关回切旧路径，不做硬回滚。

## 4. 90 天落地顺序（压缩版）

### Phase A（0-30 天）
- Search shadow read（OpenSearch/Qdrant PoC，不切用户流量）。
- Ingest workflow PoC（Temporal + Redpanda 编排一条最小 ingest 任务）。
- Contract 非阻断门禁接入（openapi diff + spectral + pact verify）。

### Phase B（31-60 天）
- Search 小流量 A/B + 切换策略。
- Ingest 接口转换后一次性切换 + 30分钟回滚窗口。
- Observability 三栈贯通（metrics/logs/traces）和基础告警上线。

### Phase C（61-90 天）
- Multi-tenant/Config 平台化落地（身份/授权；配置从.env迁到SOPS）。
- Crawler runtime 统一为 artifact/run/lineage 模型。
- Frontend 页面级绞杀完成第一批高价值页面。

## 5. 强制验收标准（跨链路）

1. 功能等价：回归用例通过率 >= 99%。
2. 性能目标：关键接口 P95 不劣化超过 10%。
3. 可观测：每条链路具备 SLI、告警规则、追踪样本。
4. 回滚能力：每次发布均有 30 分钟可验证回滚窗口。
5. 契约治理：API/Event schema 变更必须有兼容性检查记录。

## 6. 与详细文档映射

- 详细链路文档：`chains/01..07_*.md`
- LLM 专项补充：`chains/08_llm_embedded_platformization.md`
- 开源快照：`snapshots/*`
- 里程碑排期：`REFACTOR_ROADMAP.md`

本文件作为“决策入口”；详细技术论证与 PoC 命令保留在各链路文档。
