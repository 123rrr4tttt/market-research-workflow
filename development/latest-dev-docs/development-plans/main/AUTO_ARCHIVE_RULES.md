# Development Plans 自动归档规则

Last Updated: `2026-03-03 15:39 PST`

适用范围：`development/latest-dev-docs/development-plans/*`

## 1. 归档触发条件（全部满足才迁移）

1. 计划已有明确封口证据（实现、测试/运行态验收、状态结论）。
2. 主任务板中该计划对应任务状态不再是 `planned/in_progress`。
3. 索引可给出至少一个“封口主证据文档”路径。
4. 不存在“仅文档完成、代码未落地”的情况。

## 2. 禁止自动归档条件（任一命中即阻断）

1. 文档仍出现 `partial / not complete / not_closed / pending / blocked` 主结论。
2. 仅有设计稿或评估稿，无执行/验收记录。
3. 计划仍在 `CURRENT_DEV` 未完成项汇总中被标记为未完成。

## 3. 目录迁移与改名规则

1. 迁移路径：`CURRENT_DEV/<plan_dir>` -> `CLOSED_DEV/<plan_dir or renamed_dir>`。
2. 允许改名，但必须保留日期前缀：`YYYY-MM-DD-*`。
3. 改名后同步更新该目录 `README` 标题与状态描述，避免“目录在 CLOSED 但标题仍是 CURRENT”。

## 4. 索引同步规则（必须同次提交）

1. 更新 `development-plans/INDEX.md`：
- 从 `Current Development` 删除旧项。
- 在 `Closed and Archived` 增加新项。
2. 更新 `development-plans/main/index.md`：
- `Current Development` 删除旧项。
- `Closed and Archived` 增加新项。
3. 更新顶层导航（若引用到该计划）：
- `development/latest-dev-docs/README.md`
- `development/latest-dev-docs/MERGED_OVERVIEW.md`
4. 更新封口审计文档（如适用）：
- `development-plans/main/DEVELOPMENT_STREAMS_CLOSURE_AND_GAPS_*.md`

## 5. 引用一致性校验

1. 校验旧路径残留：`grep -RIn "<old_path>" development/latest-dev-docs` 应为 0。
2. 校验新路径可达：索引中的新链接文件必须存在。
3. 校验归档目录内相对链接：迁移后引用 `CURRENT_DEV` 的相对路径需按新层级修正。

## 6. 未完成项整理规则（不迁移）

1. 对未满足归档条件的计划，保留在 `CURRENT_DEV`。
2. 必须在 `CURRENT_DEV` 未完成项汇总中登记“未完成项 + 引用”。
3. 未完成项汇总文档作为下一轮推进入口，不得替代原计划文档。

## 7. 最小执行步骤（操作顺序）

1. 判定封口条件。
2. 执行目录迁移/改名。
3. 同步索引与总览引用。
4. 修复迁移后断链。
5. 运行链接与残留校验。
6. 更新未完成项汇总。
