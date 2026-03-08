# Version B（GatePlus）原子任务表与执行序列

## 1) 原子任务总表

| 任务ID | 任务名称 | 输入 | 输出 | 依赖 | 并行组 | 串行闸门 | Owner | 验收标准 | 回滚点 |
|---|---|---|---|---|---|---|---|---|---|
| B-AT-01 | 工作树与分支就绪检查 | `feature/version-B-gateplus` 当前 HEAD | baseline 记录（branch/head/status） | 无 | PG-0 | G0 | dev-owner | 工作目录独立、分支可写、git 正常 | 回到 baseline HEAD |
| B-AT-02 | GateDecision reason_code 标准化 | `meaningful_gate.py` | `GateDecision.to_dict()` 增加 `reason_code` | B-AT-01 | PG-1 | G1 | dev-owner | 每个 gate 输出可稳定聚合 reason code | 回退 `meaningful_gate.py` |
| B-AT-03 | GatePlus 聚合快照实现 | `meaningful_gate.py` | `build_gateplus_snapshot`（统一输出 blocked_stage/reason） | B-AT-02 | PG-1 | G1 | dev-owner | 可同时聚合 url/content/provenance gate | 回退 `meaningful_gate.py` |
| B-AT-04 | single_url 接入 GatePlus | `single_url.py` | 关键返回结构新增 `gate_plus` 字段 | B-AT-03 | PG-2 | G2 | dev-owner | pre-fetch/pre-write/provenance/success 均可带 gate 汇总 | 回退 `single_url.py` |
| B-AT-05 | 单元测试补充与文档索引同步 | test + docs index | gateplus 相关测试 + CURRENT_DEV 索引可导航 | B-AT-04 | PG-3 | G3 | dev-owner | 测试文件覆盖新增能力，文档路径可追踪 | 回退 tests/docs |
| B-AT-06 | 本地验证与提交归档 | 变更集 | 里程碑 commit（本地） | B-AT-05 | PG-4 | G4 | dev-owner | 通过最小验证（语法/测试命令可执行）并输出回滚点 | `git reset --soft HEAD~1` |

## 2) 执行序列（Execution Sequence）

1. **G0 前置闸门**：确认独立工作树已建立，切换 `feature/version-B-gateplus`。
2. **PG-1 并行组**：完成 gate reason code 标准化 + GatePlus 快照函数（B-AT-02/03）。
3. **G1 串行闸门**：确认 GatePlus 输出结构稳定（`checks/blocked/blocked_stage/blocked_reason`）。
4. **PG-2**：在 `single_url` 关键结果路径接入 `gate_plus`（B-AT-04）。
5. **G2 串行闸门**：确保新增字段不破坏原有 `pre_fetch_url_gate` / `pre_write_content_gate` 输出。
6. **PG-3**：补充单测与 CURRENT_DEV 索引（B-AT-05）。
7. **PG-4**：执行本地验证命令，完成里程碑提交（B-AT-06）。
8. **G4 收口闸门**：输出可运行性说明、验证结果、commit hash、剩余风险。
