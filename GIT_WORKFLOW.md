# Git 工作流（轻量版）

适用场景：当前仓库已经较大、模块较多（后端/API/迁移/前端/脚本/文档并存），需要降低改动失控风险，但不希望引入复杂流程。

## 1. 目标（软件工程视角）

- `可追踪`：知道每次改动为什么发生、改了哪里、影响什么。
- `可回退`：出问题时可以快速回到稳定版本。
- `可协作`：未来多人协作时，减少互相覆盖与冲突。
- `可发布`：给稳定节点打标签（tag），形成里程碑。

一句话：`Git 不是备份工具，而是变更管理系统。`

## 2. 分支策略（先轻量，再升级）

当前建议采用 `main + 短生命周期功能分支`：

- `main`：始终保持“可运行/可回滚”
- `feat/*`：新功能
- `fix/*`：缺陷修复
- `refactor/*`：重构（尽量不改行为）
- `docs/*`：文档
- `chore/*`：工程杂项（脚本、配置、清理）

示例：

```bash
git switch -c feat/resource-pool-search
git switch -c fix/ingest-timeout
git switch -c docs/git-workflow
```

建议：

- 大需求拆成多个分支，不要一个分支堆所有改动。
- 涉及数据库迁移时，单独一个提交（必要时单独一个分支）。

## 3. 提交规范（最重要）

原则：`一次提交只做一件事`。

推荐提交前缀（Conventional Commits 简化版）：

- `feat:` 新功能
- `fix:` 修复 bug
- `refactor:` 重构（不改外部行为）
- `docs:` 文档
- `test:` 测试
- `chore:` 杂项（配置、脚本、依赖）

示例（贴合本项目）：

```bash
git commit -m "feat: add unified resource pool search endpoint"
git commit -m "fix: handle empty site_entries in resource pool ingest"
git commit -m "refactor: split discovery service adapter mapping"
git commit -m "docs: add resource pool implementation plan"
```

不推荐：

- `update`
- `修改`
- `fix bugs`
- 一次 commit 同时包含“迁移 + API + 前端 + 文档大改”且没有说明

## 4. 日常开发节奏（适合项目变大时）

建议固定节奏：

1. 从 `main` 拉新代码
2. 新建功能分支
3. 小步提交（每 30-90 分钟一个可解释提交）
4. 自测通过后合并回 `main`
5. 删除分支

常用命令：

```bash
# 更新主分支
git switch main
git pull --ff-only

# 开发新功能
git switch -c feat/xxx

# 查看改动范围（大项目里非常重要）
git status
git diff --stat

# 分批提交（按文件/按块）
git add <files>
git commit -m "feat: ..."

# 合并完成后清理
git switch main
git pull --ff-only
git branch -d feat/xxx
```

## 5. 项目变大时的拆分方法（实用）

当你感觉“改动太大”，通常不是代码写不动，而是`变更边界不清晰`。用下面方式拆：

- `提交维度拆分`：迁移、模型、服务、API、前端、文档分别提交
- `行为维度拆分`：先重构（不改行为），再加功能
- `风险维度拆分`：高风险改动（DB schema、删除逻辑）单独提交
- `验证维度拆分`：先补测试/脚本，再改实现

一个典型拆分示例（资源池功能）：

1. `feat: add resource pool tables migration`
2. `feat: add resource pool ORM models`
3. `feat: implement unified search service`
4. `feat: expose resource pool API endpoints`
5. `feat: add resource pool management template`
6. `docs: add resource pool verification notes`

这样以后回滚、排错、review 都容易很多。

## 6. 发布与里程碑（建议尽快开始）

每当达到“可演示/可回滚”的节点，就打 tag：

```bash
git tag -a v0.1.0 -m "resource pool basic pipeline available"
git push origin v0.1.0
```

建议里程碑定义（示例）：

- `v0.1.x`：资源池主链路可跑通
- `v0.2.x`：统一搜索与自动采集增强
- `v0.3.x`：前端管理台与配置化完善

## 7. 合并前检查清单（最低成本）

提交/合并前至少检查：

- `git diff --stat` 是否符合本次目标（防止误提交）
- 是否包含不该提交的文件（临时数据、日志、密钥）
- 数据库迁移是否与模型/API 改动匹配
- 文档是否需要同步（README、设计说明、验证记录）

如果改动很大，再加一项：

- 写一句“本次改动影响范围”到提交信息或 PR 描述中

## 8. 你现在就可以执行的习惯（最有收益）

- 不在 `main` 上长期积累未提交改动
- 每次开始新方向前先开分支
- 每次提交前看一眼 `git diff --stat`
- 为稳定节点打 tag

这四件事足够把大型项目的混乱度降下来。
