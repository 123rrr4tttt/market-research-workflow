# MERGED EXECUTION PLAN (Frozen v1)

Generated: 2026-03-04 11:08:30 PST

## Source Artifacts
- C1: C1-20260304-104837.last.txt
- C2: C2-20260304-105145.last.txt
- C3: C3-20260304-105145.last.txt
- C4: C4-20260304-105441.last.txt
- C5: C5-20260304-105529.last.txt
- C6: C6-20260304-105807.last.txt
- C7: C7-20260304-105807.last.txt
- C8: C8-20260304-110044.last.txt

## Unified Goal
在不破坏当前可运行性的前提下，把 8 条链路收敛到同一套平台化边界：
- 严格接口定义 + 任务边界
- 适配器/运行时解耦
- 可灰度切换 + 可回滚
- 最小门禁（编译/构建/关键测试）

## Priority P0 (必须先做)
1. 接口与配置冻结
- 固化 contracts/envelope 与 config/env 键映射一致性。
- 结果要求：API 外部字段不破坏；新增字段仅向后兼容。

2. 采集运行时边界化
- 统一 `run_collect` 的 runtime adapter boundary，默认 legacy，可开关切 workflow/canary。
- 结果要求：sync/async 路径不改 schema；可一键回滚。

3. 搜索与索引链路最小闭环
- search/hybrid/indexer 对齐，先保证可编译可运行，再做性能优化。
- 结果要求：核心查询链路可用，失败可降级。

## Priority P1 (稳定性与运维)
4. OPS 脚本标准化
- start/restart/rollback/deploy 增加统一观测环境与 pre/post hooks。
- 结果要求：默认 no-op，不改变现有命令语义。

5. 日志与观测统一
- 统一 request/db 关键日志键，保证跨链路检索一致。
- 结果要求：不改 Prometheus 指标标签，不破坏现有监控。

6. 前端 API 契约对齐
- frontend-modern API 调用与后端新增字段对齐，确保 build 通过。
- 结果要求：页面链路不因字段扩展崩溃。

## Priority P2 (LLM 平台化)
7. LLM Provider-First 接口
- 保持“多服务商 API 接入、无需自研路由”的架构，补齐 LiteLLM/本地兜底接口。
- 结果要求：保留未来部署接口，默认策略可配置。

8. Source Library / Resource Pool 进一步收敛
- 强化 item/handler 运行边界与批量执行路径。
- 结果要求：可批量重放、失败隔离、可观测。

## Execution Order (唯一计划)
1. P0-1 接口冻结
2. P0-2 采集 runtime 边界化
3. P0-3 搜索索引闭环
4. P1-4 OPS 标准化
5. P1-5 观测统一
6. P1-6 前端契约对齐
7. P2-7 LLM provider-first
8. P2-8 source/resource 收敛

## Acceptance Gates (每阶段至少一项)
- Python: `python3 -m py_compile` 关键文件通过
- Frontend: `cd main/frontend-modern && npm run build` 通过
- Shell: `bash -n` 关键脚本通过
- Optional: 定向 pytest（环境可用时）

## Risks To Track
- 严格前端字段校验导致新增字段误判
- .venv/bin 这类环境文件被纳入变更导致跨机不可复现
- 外部 provider 不稳定时的回退策略不一致

## Next Step
按上述顺序进入逐阶段重构；每阶段产出：
- 改动文件清单
- 门禁结果
- 回滚指令
