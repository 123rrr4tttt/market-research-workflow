# MERGED DEVELOPMENT PLANS REVIEW

- Review date: 2026-03-01
- Scope: `development/latest-dev-docs/development-plans`
- Method: date/status semantics + overlap/supersession check

## 当前仍有效项（建议保留）

1. `01_plans_status-8x-2026-02-27.md`
- Reason: 仍是 8.x 总体状态面板，包含 owner/status/验收口径，适合作为上层索引。
- Note: 建议在下一次更新时补充 2026-03-01 后的实际完成度，避免与更细分任务板脱节。

2. `05_plans_project-standardization-development-directions-2026-03-01.md`
- Reason: 属于中期工程规范主线（架构/API/测试/配置/发布），未被其他文档替代。

3. `06_main_backend_docs_RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md`
- Reason: 资源库与采集配置职责划分明确，仍可作为实现分阶段蓝图。

4. `07_main_backend_docs_UNIFIED_SEARCH_ENHANCEMENT_PLAN.md`
- Reason: 增强项依赖与验收标准完整，且与当前“质量提升”目标一致。

5. `09_main_backend_docs_INGEST_CHAIN_EVIDENCE_MATRIX_2026-03-01.md`
- Reason: 同主题下信息最完整，覆盖改动证据、测试矩阵、线上隔离验证与后续诊断。

6. `10_main_backend_docs_INGEST_CHAIN_TASKBOARD_2026-03-01.md`
- Reason: 同主题下任务闭环最完整（含新增 7-10 项与 follow-ups），适合作为执行看板快照。

7. `11_main_backend_docs_NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md`
- Reason: 覆盖主干+子项目双轨路线，具备里程碑、风险与验收指标，仍有持续推进价值。

## 建议下线项（仅建议）

1. `02_plans_8x-multi-agent-kickoff-2026-02-27.md`
- Suggestion: 下线为“历史启动记录”。
- Why: 文档定位为启动稿，且明确“本轮仅状态同步”，执行价值已被后续状态/任务文档覆盖。

2. `03_plans_ingest-chain-evidence-matrix-2026-03-01.md`
- Suggestion: 下线为“短版证据矩阵（已被扩展版替代）”。
- Why: 与 `09_...EVIDENCE_MATRIX...` 同主题同日期，后者覆盖面更全、证据链更长。

3. `04_plans_ingest-chain-taskboard-2026-03-01.md`
- Suggestion: 下线为“短版任务板（已被扩展版替代）”。
- Why: 与 `10_...TASKBOARD...` 同主题同日期，后者包含更多已完成项与修复后续。

4. `08_main_backend_docs_DOC_MERGE_PLAN.md`
- Suggestion: 下线为“已执行归档计划记录”。
- Why: 标题与正文均标注“已执行”，更多是过程留痕，非当前开发计划主文档。

## 下一版更新频率建议

1. Baseline cadence: 每周一次（建议每周五）
- 更新对象: `01`, `05`, `06`, `07`, `11`
- 目标: 保持战略层计划与实际进度一致。

2. Change-driven cadence: 发生关键变更后 24 小时内补更
- 触发条件: 新增核心 API/契约、测试矩阵扩展、路由/数据模型变更、上线配置切换。
- 更新对象: `09`, `10`（证据矩阵与任务板优先）。

3. Merge/retire checkpoint: 每两周一次
- 动作: 检查是否出现“短版被长版覆盖”或“已执行记录长期未再引用”的文档。
- 输出: 在本文件追加“下线建议变更记录”。

## 推荐执行规则（下版可直接采用）

- 同主题仅保留 1 份“可执行主文档”（其余归档为历史）。
- 主文档需包含: `Last Updated`、`Owner`、`Status`、`Next Action`、`Evidence`。
- 连续 2 个周期无更新且无引用的计划文档，自动进入“建议下线候选”。
