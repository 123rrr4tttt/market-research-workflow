<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/03_B-line-round3-stage1-research-and-gate-blueprint.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-B-atomic-plan/03_B-line-round3-stage1-research-and-gate-blueprint.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Version B（GatePlus）第3轮-阶段1：先检索再开发（兼容演进/契约测试/门禁蓝图）

- 时间：2026-03-03 22:54 PST
- 阶段目标：仅完成联网最佳实践调研与本地沉淀，不改业务代码
- 关联知识池：
  - `external_refs/version-B/B-line-round3-stage1-best-practices-2026-03-03.md`

## 1) 本阶段产出摘要

围绕 B 线四个主题完成调研并落地：
1. **Schema 兼容演进**：采用“先扩展后收缩（expand/contract）”与可审计兼容级别。
2. **向后兼容测试**：建立 API surface diff + consumer snapshot + runtime fallback 三层回归。
3. **契约测试**：以现有 `tests/contract` 为基础，补 consumer 视角契约与发布前放行规则。
4. **集成门禁**：设计 G0~G5 分级门禁，PR 至少卡 G1/G2/G3。

## 2) 适用边界（针对本项目）

- 适用：`gate_plus` 这类“新增字段但不得破坏旧消费链路”的增量演进。
- 适用：`/process`、ingest、dashboard 聚合等关键 API。
- 适用：多租户 `project_<key>` schema 演进与回滚。
- 不适用：一次性离线脚本快速试验（应隔离且不并入主干门禁）。

## 3) 可执行原子任务表（下一阶段实现建议）

| 原子任务ID | 任务 | 输入 | 输出 | 依赖 | 门禁 | 风险 | 回滚 |
|---|---|---|---|---|---|---|---|
| B3-S1-AT1 | 建立兼容策略基线（字段新增/删除/重命名规则） | 知识池文档、现有 API 合约 | `compatibility-policy.md` | 无 | G0 | 规则过宽/过严 | 文档回退 |
| B3-S1-AT2 | 补 `/process` 双样例契约测试（新旧字段并存） | 当前 contract tests | 新增 contract test 文件 | AT1 | G2 | 样例覆盖不足 | 回退新增测试 |
| B3-S1-AT3 | 增加 OpenAPI/响应结构 diff 检查脚本 | 现有接口定义与响应样例 | `scripts/*compat*check*` | AT1 | G3 | 误报导致阻塞 | 脚本开关降级为 warning |
| B3-S1-AT4 | 扩展 `gateplus_ci_guard.sh` 为分级门禁入口（G1/G2/G3） | 现有脚本 | 门禁脚本 v2 | AT2,AT3 | G3 | 门禁时间过长 | 先在 PR 非阻塞试运行 |
| B3-S1-AT5 | 配置分支保护 required checks | CI job 名称 | branch protection 配置记录 | AT4 | G3 | 误配导致无法合并 | 临时移除新增 required check |
| B3-S1-AT6 | 多租户 schema 迁移回滚演练（1个样本项目） | migration 脚本、测试项目 | 演练记录与回滚证明 | AT1 | G4 | 演练污染数据 | 在隔离环境执行 + 清理脚本 |

## 4) 关键来源（官方/成熟实践）

- Confluent Schema Evolution: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
- Google AIP-180: https://google.aip.dev/180
- Zalando Backwards-compatible changes: https://opensource.zalando.com/restful-api-guidelines/#backwards-compatible-changes
- Buf Breaking: https://buf.build/docs/breaking/
- Pact Docs: https://docs.pact.io/
- Pact can-i-deploy: https://docs.pact.io/pact_broker/can_i_deploy
- GitHub Protected Branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches

## 5) 风险提示与默认回滚

- 风险1：新增字段引发旧 consumer 解析异常（隐式破坏）。
- 风险2：门禁一次性上太重，影响迭代速度。
- 风险3：多租户 schema 迁移在边缘项目失配。

默认回滚：
1. 回退到最后一个通过 G3 的 commit。
2. 关闭新增 required check（临时），恢复为观察模式。
3. DB 执行 down migration，恢复双读/旧字段路径。
