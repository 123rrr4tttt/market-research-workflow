# MERGED_PLAN

- Generated: 2026-03-01 (PST)
- Merge Scope: `development/latest-dev-docs/root-plans`
- Merge Rule: 同主题目标/动作/验收合并为单条；保留最新状态，补充来源与时间标注。

## 目录

1. Source Baseline
2. Deduplicated Program Plan
3. Milestones and Time Anchors
4. Open Follow-ups

## 1. Source Baseline

| Source File | Doc Date | Role |
|---|---|---|
| `project-standardization-development-directions-2026-03-01.md` | 2026-03-01 | 标准化总纲、工作流与里程碑 |
| `ingest-chain-taskboard-2026-03-01.md` | 2026-03-01 | ingest/source_library 执行看板与完成项 |
| `ingest-chain-evidence-matrix-2026-03-01.md` | 2026-03-01 | 已落地改动证据与测试结果 |
| `status-8x-2026-02-27.md` | 2026-02-27 | 8.x 路线状态、owner 与验收标准 |
| `RELEASE_NOTES_pre-release-0.9-rc2.0.md` | 2026-02-26, 2026-02-27, 2026-03-01 | 版本侧状态补充与测试标准化进展 |

## 2. Deduplicated Program Plan

### P0. Project Key Enforcement + Multi-project Isolation

- Status: `done (stage-1)` + `pending (stage-2 require rollout)`
- Time: `first_seen=2026-03-01` / `last_updated=2026-03-01`
- Consolidated Actions:
  - 统一 ingest/source_library 写路径 `project_key` 策略（`warn -> require` 分阶段）。
  - 中间件统一返回 `X-Project-Key-*` 与 `X-Request-Id` 观测头。
  - 保持错误码 `PROJECT_KEY_REQUIRED` 合同化。
- Acceptance (deduped):
  - `warn` 模式允许回退并记录 warning。
  - `require` 模式缺失显式 key 必须拒绝并返回结构化错误。
  - 关键写接口可验证 schema 隔离（`project_<key>`）。
- Merged From:
  - `ingest-chain-taskboard-2026-03-01.md`
  - `ingest-chain-evidence-matrix-2026-03-01.md`
  - `project-standardization-development-directions-2026-03-01.md`

### P1. API Contract and Error Envelope Standardization

- Status: `in_progress`
- Time: `first_seen=2026-02-26` / `last_updated=2026-03-01`
- Consolidated Actions:
  - 统一 API envelope：`status/data/error/meta`。
  - 统一错误分类：`error.code/error.message/error.details` + trace/request id。
  - 对破坏性变更要求弃用窗口与迁移说明。
- Acceptance (deduped):
  - 核心路由合同测试通过。
  - 新增路由不得绕过 envelope 规范。
- Merged From:
  - `project-standardization-development-directions-2026-03-01.md`
  - `RELEASE_NOTES_pre-release-0.9-rc2.0.md`

### P2. Testing and CI Gate Standardization

- Status: `baseline_done`, `coverage_expansion_in_progress`
- Time: `first_seen=2026-02-26` / `last_updated=2026-03-01`
- Consolidated Actions:
  - 分层测试：`unit/integration/contract/e2e` 与 strict markers。
  - CI 并行门禁：`unit/integration/contract/e2e/docker`。
  - 扩展到关键 ingest/search 端到端链路与 DB-backed 隔离校验。
- Acceptance (deduped):
  - PR 门禁至少覆盖 `unit + integration + docker`。
  - 主干/夜间门禁覆盖 `unit + integration + contract + e2e + docker`。
  - 关键写接口具备显式/缺失 key 双路径测试。
- Merged From:
  - `project-standardization-development-directions-2026-03-01.md`
  - `ingest-chain-taskboard-2026-03-01.md`
  - `ingest-chain-evidence-matrix-2026-03-01.md`
  - `RELEASE_NOTES_pre-release-0.9-rc2.0.md`

### P3. Observability and Ops Evidence Normalization

- Status: `in_progress`
- Time: `first_seen=2026-02-26` / `last_updated=2026-03-01`
- Consolidated Actions:
  - 统一日志字段：`request_id/project_key/project_key_source/error_code`。
  - 固化双层健康检查语义：`/health` 与 `/health/deep`。
  - 故障证据清单标准化（日志、测试工件、样例输入）。
- Acceptance (deduped):
  - 异常无需盲重跑即可基于日志和工件定位。
  - 健康端点与请求上下文头在 e2e 中持续可验证。
- Merged From:
  - `project-standardization-development-directions-2026-03-01.md`
  - `ingest-chain-evidence-matrix-2026-03-01.md`
  - `RELEASE_NOTES_pre-release-0.9-rc2.0.md`

### P4. Config, Migration, and Runtime Predictability

- Status: `in_progress`
- Time: `first_seen=2026-02-27` / `last_updated=2026-03-01`
- Consolidated Actions:
  - 环境变量命名/必需性/敏感项与 `.env.example` 一致化。
  - migration 命名、回滚说明、兼容性影响模板化。
  - local 与 docker 运行差异矩阵持续维护。
- Acceptance (deduped):
  - 生产路径无隐藏 env 依赖。
  - migration 具备可审查、可复现、可回退说明。
- Merged From:
  - `project-standardization-development-directions-2026-03-01.md`
  - `status-8x-2026-02-27.md`

### P5. 8.x Product/Capability Track (Deduped)

- Status: mixed (`done/partial/in_progress/planned`)
- Time: `first_seen=2026-02-27` / `last_updated=2026-03-01`
- Consolidated Backlog:
  - 8.1 来源池自动提取与整合：`done`，补文档阈值与最小回归。
  - 8.2 工作流平台化：`partial`，推进模板保存-回读-运行闭环增强。
  - 8.3 Perplexity 集成：`planned`，补 provider 适配与融合策略。
  - 8.4 时间轴与实体演化：`in_progress`，补 schema + 版本查询 API。
  - 8.5 RAG + 报告：`partial`，补对话与报告最小闭环。
  - 8.6 对象化信息收集：`partial`，统一 company/product/operation 模型。
  - 8.7 数据类型优化：`in_progress`，输出 schema 约束与回归校验。
  - 8.8 其他迭代：`in_progress`，适配器可靠性、占位项、脚本复用。
- Acceptance (deduped):
  - 各子项均要求“可执行闭环 + 对应最小回归/验证证据”。
- Merged From:
  - `status-8x-2026-02-27.md`
  - `RELEASE_NOTES_pre-release-0.9-rc2.0.md`

## 3. Milestones and Time Anchors

- 2026-02-26: `v0.9-rc2.0` 预发布，主链路稳定化开始。
- 2026-02-27: 8.x 状态口径同步（done/partial/in_progress/planned 分类）。
- 2026-03-01: project key 分阶段治理、证据矩阵、测试与 CI 标准化基线形成。
- 2026-03-01 + 1-2 weeks: 阶段目标聚焦 `require` 强制切换、关键 e2e 扩展、schema 隔离集成验证。
- 2026-03-01 + 3-4 weeks: 扩展阶段聚焦关键业务 e2e 覆盖与流程模板全面落地。

## 4. Open Follow-ups

- 切换 `project_key_enforcement_mode=require` 前，先完成客户端显式传 key 覆盖检查。
- 增补 `/api/v1/ingest/graph/structured-search` 与 `/api/v1/source_library/items/{item_key}/run` 的 API 级测试样例。
- 增补 DB-backed 集成测试，验证 `project_demo_proj` 与其他 `project_<key>` 的隔离性。
- 对 8.3/8.5/8.6 形成按周验收清单，避免长期停留在 `planned/partial`。
