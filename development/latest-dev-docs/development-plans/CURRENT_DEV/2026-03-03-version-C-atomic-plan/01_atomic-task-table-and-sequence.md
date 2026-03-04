# Version C 原子任务表与执行序列

## 1) 原子任务总表

| 任务ID | 任务名称 | 输入 | 输出 | 依赖 | 并行组 | 串行闸门 | Owner | 验收标准 | 回滚点 |
|---|---|---|---|---|---|---|---|---|---|
| C-AT-01 | 分支状态确认与基线检查 | `feature/version-C-streamplus` 当前 HEAD | 基线记录（branch/head/status） | 无 | PG-0 | G0 | docs-owner | 分支可读、工作树状态可识别 | 回到基线 HEAD |
| C-AT-02 | 原子任务文档补建 | 缺失文档路径规范 | `01_atomic-task-table-and-sequence.md` | C-AT-01 | PG-1 | G1 | docs-owner | 文档包含必填字段且结构完整 | 删除新增文档 |
| C-AT-03 | 索引更新 | 文档相对路径 | README/INDEX/MERGED_OVERVIEW 索引条目 | C-AT-02 | PG-1 | G1 | docs-owner | 索引可追踪到原子任务文档 | 回退索引文件 |
| C-AT-04 | 文档一致性校验 | 文档与索引文件 | 校验记录（存在性+可导航性） | C-AT-03 | PG-2 | G2 | docs-owner | 路径存在，索引跳转无断链 | 回退到 C-AT-03 前 |
| C-AT-05 | 提交归档 | 已暂存文档变更 | 单次 docs commit | C-AT-04 | PG-3 | G3 | docs-owner | commit message 与版本一致 | `git reset --soft HEAD~1` |

## 2) 执行序列（Execution Sequence）

1. **G0 前置闸门**：确认处于 `feature/version-C-streamplus` 且可执行文档修复。
2. **PG-1 并行组**：
   - 生成原子任务主文档（C-AT-02）
   - 同步更新索引（C-AT-03）
3. **G1 串行闸门**：检查主文档字段完整性（任务ID、输入输出、依赖、并行组、串行闸门、owner、验收标准、回滚点）。
4. **PG-2**：执行存在性与索引可达性校验（C-AT-04）。
5. **G2 串行闸门**：确认仅文档变更、无代码修改。
6. **PG-3**：执行单次提交（C-AT-05）。
7. **G3 收口闸门**：输出 commit hash 与文档存在性检查结果。
