# 预发布说明：v0.1.8-rc1（2026-04-07）

- 版本类型：`Release Candidate（预发布）`
- 版本名称：`v0.1.8-rc1`
- 适用场景：内部联调、主链路回归、发布前验收
- 不建议：作为长期稳定生产基线

## 摘要

本版本聚焦把 `agent-batch`、自然语言批量命令、ingest 主链路补齐与 modern 前端联动收敛到一个可回归、可回滚、可继续发布的小版本节点。

## 本次重点更新

### 1. Agent Batch 与自然语言任务入口补齐

- 新增和收敛 `agent_batch` 主链路能力，覆盖批量 submit、approval、rule-set 校验与自然语言命令入口。
- 批量任务执行绑定、lane 路由、approval argv 生成与 executor health 检查已形成可验证闭环。
- `nl-command` 路径可把自然语言指令规划为批量任务，并在需要时回写 loop metadata 与 completion 结果。

### 2. Ingest / Runtime 主干继续打通

- recent changes 已将 P1 并行 batch API、retry flow 与 runtime smoke 串到同一条开发验证链路上。
- 主干采集命令和 source-library / market 搜索路径保持对齐，便于后续继续向稳定发布收敛。
- 回滚演练 dry-run 继续保留在预发布门禁中，确保最小回退路径仍然可执行。

### 3. Modern 前端联动与图谱页稳定化

- `GraphPage` 处理了大体量 hook 依赖与 3D/2D 交互状态切换中的 lint 风险点，当前预发布门禁下已无前端 eslint warning。
- `OpsPage` 的 session artifact 选择逻辑做了 memo 稳定化，避免依赖在 render 间抖动。
- 图谱选择、悬停、自动聚焦和 selection mode 的回调依赖已收敛，适合作为这一轮预发布前端基线。

### 4. API Guard 收敛

- `agent_batch.py` 中本轮新增的 `HTTPException(detail=...)` 已全部收口，不再触发 API-layer import guard 的新增项告警。
- 对应 allowlist 已同步清理，当前 guard 输出恢复到无新增、无陈旧项。

## 预发布门禁结果

本版本在仓库当前工作区上已通过最小预发布门禁：

- 前端 lint：`PASS`
- 后端 targeted tests：`PASS`
- rollback drill dry-run：`PASS`
- metrics schema：`PASS`

报告文件：

- `.codex-artifacts/pre_release_min_gate_report.json`

## 已知非阻塞事项

- 后端仍存在若干三方库 deprecation warning：
  - `langchain.cache.SQLiteCache` 导入弃用
  - 部分 `pydantic` V2 迁移告警
- 这些警告当前不阻塞本次 `v0.1.8-rc1` 预发布，但建议在下一轮稳定化时单独清理。

## 建议打 tag 的命令

```bash
git add main/frontend-modern/package.json \
        main/frontend-modern/src/pages/GraphPage.tsx \
        main/frontend-modern/src/pages/OpsPage.tsx \
        main/backend/app/api/agent_batch.py \
        main/backend/docs/API_LAYER_HTTP_EXCEPTION_DETAIL_ALLOWLIST.txt \
        RELEASE_NOTES_v0.1.8-rc1.md

git commit -m "chore: prepare v0.1.8-rc1 prerelease"
git tag -a v0.1.8-rc1 -m "v0.1.8-rc1"
git push origin main
git push origin v0.1.8-rc1
```

## 推荐回归清单

1. `agent-batch` submit / retry / approval / nl-command 路径至少各跑一遍正向用例。
2. `Ingest` 主链路从提交到任务状态回写至少跑一遍。
3. `GraphPage` 在 2D / projection / force3d 三种视图下切换并验证 hover、selection、node card 行为。
4. `OpsPage` 中 session、artifact、task 三类选择联动验证一次。
5. 再执行一次 `./scripts/pre_release_min_gate.sh`，确保打 tag 前工作区仍保持通过。

## 说明

- 当前 Git 描述基线为 `v0.1.7-rc1` 之后的继续开发快照，本次建议以 `v0.1.8-rc1` 作为新的预发布节点。
- 历史版本说明可参考：
  - `RELEASE_NOTES_v0.1.0-rc.1.md`
  - `RELEASE_NOTES_pre-release-0.md`
  - `RELEASE_NOTES_pre-release-0.9-rc2.0.md`
