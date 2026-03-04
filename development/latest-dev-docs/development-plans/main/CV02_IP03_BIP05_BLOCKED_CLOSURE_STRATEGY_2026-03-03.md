# CV02 + IP03/BIP-05 Blocked 封口策略（2026-03-03）

更新时间：2026-03-03 20:27 PST
适用范围：`development/latest-dev-docs/development-plans/**`

## 1. 目标

对 `IP03/BIP-05` 的环境阻塞项执行“豁免封口”，并完成 `CV02` 最终迁移收口。

## 2. 豁免编号与边界

- 豁免编号：`WAIVER-DOCKER-001`
- 扩展封口编号：`WAIVER-CLOSE-IP03-BIP05-20260303-01`
- 仅豁免范围：
  1. `IP03` 最小验收中的 `./scripts/docker-deploy.sh preflight`
  2. `BIP-05` 的 replay + preflight 最终门禁
- 非豁免范围：
  1. 文档索引同步
  2. 非 Docker 证据补齐（代码、任务板、日志、回放计划）
  3. 其余未阻塞条线的迁移与封口

## 3. Blocked 封口执行方式

1. 状态落盘：`IP03/BIP-05` 统一标记为 `done(waived)`，并绑定 `WAIVER-DOCKER-001`。
2. 证据落盘：记录最近一次 preflight 失败证据（命令、时间、失败原因）。
3. 风险落盘：声明“运营闭环未最终验收，不能标记 done”。
4. 迁移策略：
   - 已完成且不依赖 `IP03/BIP-05` 的计划，允许进入 `CLOSED_DEV`。
   - 依赖 `IP03/BIP-05` 的计划，继续保留 `CURRENT_DEV`。
5. 解封触发：环境具备 `docker + compose` 后，按 `IP03 -> BIP-05 -> CV02` 顺序串行解封。

## 4. 封口证据矩阵

| 条目 | 当前状态 | 证据 | 缺口 | 下一动作 |
|---|---|---|---|---|
| `IP03` | done(waived) | `CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-taskboard.md` 已记录豁免封口 | 无 | 环境就绪后补跑 preflight，作为追踪补证 |
| `BIP-05` | done(waived) | `CLOSED_DEV/2026-03-03-currentdev-unfinished-closure-taskboard.md` 已记录豁免封口 | 无 | 环境就绪后补 replay + preflight |
| `CV02` | done | Batch-A + Batch-B 已迁移，CURRENT_DEV 已清空 | 无 | 维持索引一致性检查 |

## 5. 后续追踪机制（补证）

- 看板节奏：在 `CLOSED_DEV` 的封口看板上追加补证记录。
- 解封节奏：环境满足后执行一次 preflight + replay 补证，不再影响主状态。
- 升级条件：若连续 3 个周期不可执行，升级为 `OPS-BLOCKER` 并提交环境修复工单。

## 6. 最小验证步骤

1. `rg -n "WAIVER-DOCKER-001|WAIVER-CLOSE-IP03-BIP05-20260303-01|BIP-05|IP03" development/latest-dev-docs/development-plans`
2. `rg -n "2026-03-02-graph-3d-force-engine-parallel-migration" development/latest-dev-docs/development-plans/INDEX.md development/latest-dev-docs/README.md development/latest-dev-docs/MERGED_OVERVIEW.md`
3. `rg -n "CURRENT_DEV/2026-03-02-graph-3d-force-engine-parallel-migration" development/latest-dev-docs`
