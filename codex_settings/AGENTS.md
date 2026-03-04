# Codex 工作约定

## 任务执行前检查

在开始执行每个任务前，**简要判断**是否适合调用 multi-agent 技能（`multi-agent-parallel-development`）：

- 若任务涉及 **3 个及以上独立子项**、**多文件/多目录改动** 或 **多维度审查**（安全/质量/bug 等），优先考虑使用 spawn_agent 并行执行；若适用，先说明「本任务适合多 Agent 并行」，再按该技能流程拆解并执行。
- **若仅需单 Agent**：直接自己干活，无需说明「不适合多 Agent」或做任何额外判断，直接按常规流程执行即可。
- 判断应快速完成，不拖慢简单任务。

## 触发词自动流程（蜂群）

- 当用户消息匹配 `蜂群[<文件路径>]` 或 `蜂群【<文件路径>】` 时，立即进入蜂群文件流程，无需再次确认。
- 流程入口命令：`bash ./codex_settings/scripts/swarm_file_bootstrap.sh "<文件路径>"`。
- 多文件批量入口命令：`bash ./codex_settings/scripts/swarm.sh -j 4 -r 1 "<文件1>" "<文件2>" ...`。
- 如果路径不存在：先返回错误与可选候选路径（最多 5 个），停止后续流程。

### 蜂群文件流程（固定步骤）

1. 运行 bootstrap 脚本，读取上下文摘要（文件信息、符号、引用关系）。
2. 并行启动 3 个子任务（可用 subagent 或并行工具调用）：
   - `explore`：定位该文件的调用方与依赖方。
   - `reviewer`：检查正确性/安全性/测试风险。
   - `impact`：评估修改影响面与最小回归验证集合。
3. 主 Agent 汇总为统一结构输出：`现状`、`风险`、`可改动方案`、`最小验证步骤`。
4. 若用户未明确要求“执行修改”，默认只给方案与命令，不改文件。
5. 若用户追加“执行修改”，按最小改动原则实施并执行门禁检查。

## 并行开发规范（高吞吐极简版 v2）

- 原子任务：每个任务只做一件事，必须有 `目标/输入/输出/验收`。
- 自动门禁：每个任务完成后自动执行最小检查（`lint/test/契约校验` 至少其一）。
- 失败隔离：失败任务只重试自身，不阻塞其他并行任务；仅瞬时失败可重试。
- 统一回传：subagent 固定回传 `结果/改动文件/验证状态/风险`，便于主 Agent 自动汇总。
- 低耦合并行：仅无依赖任务并行，依赖链保持串行；同文件冲突先合并再继续。
- 默认幂等：可重放任务重复执行结果一致，避免重复写入和状态污染。

## 修改前

- 先读相关代码与文档，确认影响范围，避免盲目改动。
- 若项目有 `.cursor/rules` 或 `main/*/docs/`，优先查阅再实现。

## 修改后

- 改动完成后运行项目内测试或 lint（如 `pytest`、`npm run lint`、`./scripts/docker-deploy.sh preflight` 等），确保无回归。
- 若项目默认 Docker 运行，测试优先在 Docker 环境执行。

## 风格与范围

- 代码主体用英文，注释可用中文；以完成目标为重，不过度发散。
- 新增 API 时遵循项目既有 envelope 与分层（如 `status/data/error/meta`、`API -> services -> adapters`）。

## 开发文档目录规范（`development/`）

- `development/latest-dev-docs/` 是本项目开发文档的**重要索引与第一入口**。
- 处理开发说明相关任务时，优先在该目录完成检索、落盘与索引更新。
- 每个子项目目录（如 `root-plans`、`backend-core`、`backend-docs`、`ops-frontend`、`development-plans`）统一规则：
  - `main/`：主文档目录，仅放该子项目的合并主文档（`MERGED_*.md`）与 `main/index.md`。
  - 其他分类目录（如 `A_ARCHITECTURE`、`B_API`、`C_INGEST`、`D_TEST`、`E_OPS`、`F_PLAN`、`G_REVIEW`）：归档目录，单列展示，按主题追溯历史材料。
  - 子项目根 `INDEX.md`：必须先指向 `main/`，再列出归档目录。
- 新增/迁移开发说明时：
  - 优先写入对应子项目 `main/` 或归档目录。
  - 同步更新该子项目 `INDEX.md`。
  - 同步更新顶层导航：`development/latest-dev-docs/README.md` 与 `development/latest-dev-docs/MERGED_OVERVIEW.md`。
  - 若文档内容更新日期发生变化，文档所在目录名中的日期与文件名尾部日期必须同步更新为同一天（`YYYY-MM-DD`），并同步修正全仓库引用路径。
- 禁止只在零散路径保留“唯一副本”而不进入 `development/latest-dev-docs`（避免遗漏归档与断链）。
