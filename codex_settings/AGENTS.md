# Codex 工作约定

## 执行形态

- 遵循全局 `~/.codex/AGENTS.md` 的并行与模型路由规则；不要在项目级重复维护旧触发表。
- 任务可拆成独立验收、写入边界不冲突的工作包时，可直接使用 Codex 内置子 Agent 或并行工具推进。
- 主 Agent 负责设计、抽象判断、任务边界和最终整合；明确实现、检索、整理、批处理等工作可交给 DeepSeek 子 Agent。
- 简单任务直接主线推进，不为了形式制造并行。

## 修改前

- 先读相关代码与文档，确认影响范围，避免盲目改动。
- 若项目有 `.cursor/rules` 或 `main/*/docs/`，优先查阅再实现。

## 修改后

- 改动完成后运行项目内测试或 lint（如 `pytest`、`npm run lint`、`./scripts/docker-deploy.sh preflight` 等），确保无回归。
- 若项目默认 Docker 运行，测试优先在 Docker 环境执行。

## 风格与范围

- 代码主体用英文，注释可用中文；以完成目标为重，不过度发散。
- 新增 API 时遵循项目既有 envelope 与分层（如 `status/data/error/meta`、`API -> services -> adapters`）。


## 市场工作流 development 文档

- 本节只适用于 market-research-workflow 项目，不作为全局 Codex 规则外溢到其他仓库。
- `development/latest-dev-docs/` 是本项目开发文档第一入口；优先查看 `README.md`、`MERGED_OVERVIEW.md` 和 `index.md`。
- 当前顶层目录按最新结构使用：`root-plans/`、`backend-core/`、`backend-docs/`、`ops-frontend/`、`frontend-modern/`、`development-plans/`、`automation-runs/`。
- 子项目目录优先从本目录的 `INDEX.md` 进入；主文档入口通常是 `main/index.md`，分类目录按实际存在的 `A_ARCHITECTURE`、`B_API`、`C_INGEST`、`D_TEST`、`E_OPS`、`F_PLAN`、`G_REVIEW` 使用。
- `development-plans/` 的当前状态以 `CURRENT_DEV/INDEX.md` 为准；target 范围以 `TARGET_TOPIC_ALLOWLIST.json` 为准；外部阻塞以 `EXTERNAL_BLOCKER_MANIFEST.v1.json` 为准。
- 归档按最新目录区分：`ARCHIVE_CLOSED/`、`ARCHIVE_EXTERNAL_BLOCKED/`、`ARCHIVE_RETIRED/`。
- 新增或迁移开发说明时，写入对应子项目 `main/`、分类目录、归档目录或 `automation-runs/<lane>/`；同时更新最近的 `INDEX.md`。只有导航或当前状态变化时，才同步顶层 `README.md` 与 `MERGED_OVERVIEW.md`。
- 不要把当前开发说明的唯一副本留在零散路径；若证据或历史材料必须留在其他位置，应从 `development/latest-dev-docs` 的相应索引链接过去。

## 结构迁移与能力保全

- migration/refactor/successor/backend replacement/code generation 必须先建立 legacy/donor semantic movement inventory；locator/file/module/cell/test count 只是定位证据，不是能力完整性。
- 每条 movement 必须记录 source object、target object、named transformation、owner、effect/failure/resource/authority/recovery/projection-loss、source evidence、target realization、acceptance trace。
- disposition 仅允许：`PRESERVED_AS`、`MOVED_TO`、`REIMPLEMENTED_AS`、`DECLARED_LOSS`、`EXPLICITLY_REJECTED`、`UNASSIGNED_BLOCKER`。
- `UNASSIGNED_BLOCKER > 0` 时禁止 capability/family/phase/candidate promotion 与 legacy retirement；generator/parallel worker 只能消费已通过 completeness gate 的 spec，worker completion 不等于 promotion。
- 未生产接线或 contract-only 的能力必须明确落位或拒绝，不能因没有 live owner 被删除。
- review 必须同时做 declared-scope correctness 与 predecessor-to-successor completeness；绿色测试与精确哈希只证明声明范围，不能证明能力面无损。
- 长期唯一主规范：`docs/governance/semantic-movement-completeness-standard.md`，结构迁移与总体审核一律以此为准。

## Mechanical Implementation Routing

- IO 契约固定后的机械化开发默认交给 DeepSeek：批量代码实现、机械重构、样板/fixture/测试生成、文档同步、格式化、确定性序列化/哈希脚本等。
- 主线/高推理模型负责架构、semantic movement inventory/matrix、normative/frozen authority、风险接受、promotion、整合与最终审核。
- 每个 DeepSeek 包必须声明 目标/输入/输出/允许读写范围/验收，必须知道自己不是唯一执行者，不得扩大语义或回退他人改动，固定回传 结果/改动文件/验证/风险。
- DeepSeek 不得自行修改 frozen semantics、决定 authority/cutover/promotion，也不得把绿色测试当完成。
- 机械生成必须先通过 semantic movement completeness gate。


## 自动化回复语言

- 所有自动化、提醒、监控、定时任务和线程唤醒的面向用户回复默认使用中文。
- 代码标识、命令、路径、API 字段、错误原文、引用标题和必须保留的外部原文可保持原语言。
