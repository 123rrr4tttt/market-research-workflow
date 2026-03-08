# C线第3轮-阶段1：先检索再开发（最佳实践调研落地）

## 目标与约束
- 目标：围绕 C 线四个主题形成可执行门禁方案与原子任务输入。
- 约束：本阶段仅调研与文档沉淀，不改业务代码。
- 四个主题：
  1) 最小发布门
  2) 可观测门禁
  3) 报告结构化
  4) pre-release 脚本工程化

---

## 调研摘要（可直接转实现输入）

### A. 最小发布门（发布最小可行安全线）
- 基线来自 GitHub branch protection + required status checks。
- 建议最小门：
  - main/release 禁止直推，必须 PR；
  - CI 至少 `lint/test/build` 必过；
  - pre-release 必须产出结构化 changelog；
  - 产物可追溯 commit SHA 与可回滚 tag。
- 关键收益：先建立“不会把坏版本放行”的最小安全线。

### B. 可观测门禁（发布前先证明可看见、可定位）
- 基线来自 OTel（3 信号 + 语义约定 + 上下文传播）与 Prometheus/SRE 告警实践。
- 建议最小门：
  - 关键路径必须可观测（trace/metric/log）；
  - 日志带 trace_id/span_id；
  - 告警优先对齐“用户症状/SLO 风险”，避免底层噪声；
  - pre-release 可观测检查不过则不放行。
- 关键收益：避免“发布后不可诊断”。

### C. 报告结构化（人机双可读）
- 基线来自 Keep a Changelog + Schema 化思路（OpenAPI 作为结构标准参考）。
- 建议固定 4 类报告产物：
  - gate-result.json
  - quality-metrics.json
  - observability-check.json
  - release-notes.md
- 关键收益：实现自动聚合、可比较、可审计。

### D. pre-release 脚本工程化（可维护、可测试、可复用）
- 基线来自 GitHub reusable workflows + shellcheck + bats + pre-commit。
- 建议最小工程化要求：
  - 脚本按 collect/check/report/publish 分层；
  - 幂等执行；
  - shell 静态检查 + 单测覆盖关键分支；
  - 统一错误码与日志前缀。
- 关键收益：减少脚本腐化，降低“临发版手工补洞”。

---

## 来源链接（官方/成熟开源）
- GitHub protected branches:
  - https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- GitHub reusable workflows:
  - https://docs.github.com/en/actions/sharing-automations/reusing-workflows
- OpenTelemetry observability primer:
  - https://opentelemetry.io/docs/concepts/observability-primer/
- OpenTelemetry context propagation:
  - https://opentelemetry.io/docs/concepts/context-propagation/
- OpenTelemetry semantic conventions:
  - https://opentelemetry.io/docs/concepts/semantic-conventions/
- Prometheus alerting best practices:
  - https://prometheus.io/docs/practices/alerting/
- Google SRE Workbook（SLO 告警）:
  - https://sre.google/workbook/alerting-on-slos/
- Keep a Changelog:
  - https://keepachangelog.com/en/1.1.0/
- OpenAPI Spec 3.1:
  - https://spec.openapis.org/oas/v3.1.0
- ShellCheck:
  - https://github.com/koalaman/shellcheck
- bats-core:
  - https://github.com/bats-core/bats-core
- pre-commit:
  - https://pre-commit.com/

---

## 适用边界
- 本方案优先适配“单仓 + 单主发布流水线”的 C 线当前阶段。
- 暂不覆盖：
  - 多仓联邦发布一致性；
  - 全域 SLO 分层治理；
  - 企业级合规产物（如 SBOM 强制门）。

---

## 风险与回滚策略
1. 门禁一次性过严导致流程阻塞
   - 策略：`warning-only -> blocking` 两阶段灰度。
2. 指标基线不稳导致误报
   - 策略：先跑 3 轮影子发布，校准阈值后再阻断。
3. 脚本重构影响现有手工流程
   - 策略：保留 legacy 入口一个迭代周期，按 flag 切换。
4. 报告 schema 频繁变更
   - 策略：冻结 v1，新增字段只增不删。

---

## 建议原子任务表（供下一阶段实现编排）

| ID | 原子任务 | 产出 | 依赖 |
|---|---|---|---|
| C3-S1-T01 | 定义最小发布门 v1（分支/检查/回滚锚点） | `gate-policy-v1.md` | 无 |
| C3-S1-T02 | 梳理当前 CI 检查映射到 required checks | `required-checks-map.md` | T01 |
| C3-S1-T03 | 定义可观测门 v1（覆盖/关联/告警） | `observability-gate-v1.md` | 无 |
| C3-S1-T04 | 产出 pre-release 报告 schema v1 | `report-schema-v1.json` + `release-notes-template.md` | T01,T03 |
| C3-S1-T05 | pre-release 脚本分层设计（collect/check/report/publish） | `pre-release-script-architecture.md` | T04 |
| C3-S1-T06 | 设计脚本质量门（shellcheck+bats+pre-commit） | `script-quality-gate-v1.md` | T05 |
| C3-S1-T07 | 影子运行方案（warning-only）与阻断切换条件 | `gate-rollout-plan.md` | T02,T03,T06 |
| C3-S1-T08 | 回滚与审计手册（故障演练） | `rollback-runbook-v1.md` | T07 |

---

## 本阶段落盘说明
- 知识池沉淀：`信息源库/global/research/2026-03-03-C-line-round3-stage1-best-practices.md`
- 当前开发文档：`CURRENT_DEV/2026-03-03-version-C-atomic-plan/03_C-line-round3-stage1-best-practice-research.md`

> 结论：已完成“先检索再开发”的阶段1输入，下一步可按上述原子任务进入并行实现与门禁接线。