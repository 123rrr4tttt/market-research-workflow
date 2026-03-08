# Atomic Task List: Abstract Planning Folderization (2026-03-07)

## 定位

本任务清单只用于推动 `抽象规划.md` 的主题拆分与子目录起步文档建立。

详细需求细化和实现级任务分解，不在本清单内预写死，而是交由后续各子 agent 在对应主题目录中继续完成。

## 全局规则

- `A1` 先完成，先冻结主题分组和命名。
- `A2` 完成后，各主题目录可并行创建。
- 各主题目录中的详细写作由对应子 agent 独立负责。
- 所有目录与文件命名必须符合现有开发文档规范。
- 所有新目录建立后，统一回写索引。
- 总任务只提供框架，不提前替子 agent 把各主题写成重型方案。

## Task A1: Freeze Topic Grouping

- 目标: 根据 `抽象规划.md` 冻结本轮要拆分的主题分组。
- 产出:
  - 主题列表
  - 目录命名
  - 条目归属关系
- 验收:
  - 每条原始安排都能归到一个主主题
  - 不要求在此阶段展开详细实现方案

## Task A2: Create Folder Skeletons

- 目标: 为每个主题创建子目录和基础文档骨架。
- 产出:
  - 每个主题一个目录
  - 每个目录至少包含：
    - `01_<topic>-plan-2026-03-07.md`
    - `02_atomic-tasklist-<topic>-2026-03-07.md`
- 验收:
  - 目录可从索引进入
  - 命名与日期一致
  - `01/02` 文档标题与主题一致

## Task A3: Seed Child-Agent Writing Baseline

- 目标: 为每个主题准备足够的起步信息，让子 agent 能继续写，而不是从空白开始。
- 起步信息至少包括:
  - 该主题的核心问题
  - 该主题的初步范围
  - 该主题与其他主题的边界
  - 子 agent 应优先查阅的现有代码或文档方向
- 验收:
  - 每个主题目录的 `01/02` 文档都能支撑后续继续细化
  - 子 agent 不需要重新猜测主题目标

## Task A4: Let Child Agents Expand Each Topic

- 目标: 让各子 agent 按开发文档规范继续写作各主题文档。
- 写作要求:
  - 进一步明确该主题的需求
  - 给出该主题的初步开发流程
  - 说明范围、非目标、依赖和最小验证
- 说明:
  - 细化重点在各主题目录内完成
  - 本总任务不预先替子 agent 写满所有细节
- 验收:
  - 每个子目录的 `01/02` 文档已具备继续推进所需的基本信息
  - 子 agent 输出仍聚焦需求澄清与初步流程设计

## Task A5: Sync Indexes

- 目标: 将新目录和文档同步到各级索引。
- 范围:
  - `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md`
  - `development/latest-dev-docs/development-plans/INDEX.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
- 验收:
  - 新目录均可从索引进入
  - `抽象规划.md` 不再是唯一入口

## 最小门禁

- 新目录存在且命名规范。
- 每个目录都有 `01/02` 两份起步文档。
- 每个目录的 `01/02` 已写入最基本的主题范围与流程提示。
- 索引已同步。
