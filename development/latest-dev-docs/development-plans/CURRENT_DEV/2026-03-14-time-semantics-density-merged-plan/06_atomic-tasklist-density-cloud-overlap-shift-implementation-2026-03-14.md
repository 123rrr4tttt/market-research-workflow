# 06 原子任务单增强版（Density Cloud + Overlap + Shift）

来源基线：`06_atomic-tasklist-density-cloud-overlap-shift-implementation-2026-03-14.md`  
编写日期：2026-03-14  
适用范围：`main/backend`（策略计算、API 契约、日志、离线评估、发布门禁）

## 1. 原子任务增强清单

### AT-01 `target_overlap` 入策略主链路
- 目标：让 `target_overlap` 实际影响 `shift_signal` 或窗口评分，不再仅透传。
- 输入：`query_prompt_time_density_priority(...)` 当前实现；`vector_overlap`/`target_overlap` 参数。
- 输出：包含 `target_overlap` 偏差项的新评分逻辑与注释。
- 依赖：
  - 前置：无。
  - 并行可行：可与 AT-03/04/05/06/10 并行。
  - 后继影响：AT-04/05 回归测试口径；AT-07 日志字段语义。
- DoD：
  - 代码层：评分函数新增 `target_overlap` 偏差项，且默认值兼容历史行为。
  - 观测层：同输入下仅改变 `target_overlap` 可导致排序变化或 `p_new` 变化。
  - 测试层：新增/更新单测覆盖“目标重叠度变化 -> 输出变化”。
- 失败回滚：
  - 方案 A：通过 feature flag（如 `ENABLE_TARGET_OVERLAP_EFFECT=false`）回退到旧逻辑。
  - 方案 B：回滚策略参数至“无偏差项”组合并保持 API 字段不变。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/core_business/test_process_consistency_core_contract.py
```

### AT-02 overlap 估计从启发式升级到 O1 接口
- 目标：提供可替换 O1 embedding 计算入口，同时保留启发式回退。
- 输入：`estimate_window_overlap(...)`；窗口语义表示与 query 表示。
- 输出：`vector_overlap_provider` 抽象（或等价扩展点）及回退路径。
- 依赖：
  - 前置：无。
  - 并行可行：可与 AT-01/03/04/05/06/10 并行。
  - 后继影响：AT-03 契约稳定性；AT-07 日志完整性。
- DoD：
  - provider 可用时命中 O1 路径；不可用时自动回退启发式且不中断请求。
  - provider 超时/异常有明确告警日志与降级标记。
  - 单测至少覆盖“命中 provider”“provider 异常回退”两类场景。
- 失败回滚：
  - 配置切换 `VECTOR_OVERLAP_PROVIDER=heuristic` 强制启发式。
  - 保留接口壳，不删除新增字段，避免连带回滚 API 契约。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/services -k "overlap and (provider or fallback)"
```

### AT-03 优先级结果字段契约补强
- 目标：将 `noun_group_id/vector_overlap/shift_signal/p_base/p_new/kl_to_base` 设为强校验字段。
- 输入：`/stats/prompt-time-density/priority` 响应体；既有 core contract 测试。
- 输出：更新后的契约测试断言与字段类型断言。
- 依赖：
  - 前置：AT-01/02 建议先完成以减少反复改测试夹具。
  - 并行可行：可与 AT-04/05/06 并行。
  - 后继影响：AT-07 日志字段一致性校验。
- DoD：
  - 缺字段、字段类型错误、空值越界可稳定触发失败。
  - CI 下契约测试稳定（无随机失败）。
- 失败回滚：
  - 暂时降级为 warning 断言（仅限短期修复窗口），并记录技术债。
  - 下一次修复窗口恢复 hard assert。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/core_business/test_process_consistency_core_contract.py
```

### AT-04 `avoid_peak` 退化路径回归测试
- 目标：确保 `avoid_peak=false` 时 `p_new == p_base`（容差内）。
- 输入：`redistribute_window_probabilities(...)`；priority API。
- 输出：单测与 API 回归用例。
- 依赖：
  - 前置：AT-01 完成后再锁定基线更稳妥。
  - 并行可行：可与 AT-03/05/06 并行。
  - 后继影响：AT-09 门禁阈值解释。
- DoD：
  - 关闭 avoid_peak 时 `KL≈0`，`max|p_new-p_base|` 在容差内。
  - 不同窗口数量（2/4/8）均通过。
- 失败回滚：
  - 若新逻辑破坏退化路径，临时固定 `avoid_peak=false` 为旧行为并阻断上线。
  - 回滚仅作用于概率重分配模块，不回滚 API 输出字段。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/services -k "avoid_peak and degrade"
```

### AT-05 `delta_max/tau` 约束极值测试
- 目标：验证 `delta_max` 与 `tau` 对 `p_new` 的硬约束生效。
- 输入：`redistribute_window_probabilities(...)`。
- 输出：边界测试（多窗口、极端 `shift_signal`、高重叠/低重叠）。
- 依赖：
  - 前置：AT-01 完成后口径固定。
  - 并行可行：可与 AT-03/04/06 并行。
  - 后继影响：AT-10 参数治理边界合法性。
- DoD：
  - 所有测试样例满足 `max|p_new-p_base| <= delta_max`。
  - 所有测试样例满足 `KL <= tau`。
  - 约束冲突时有确定性处理顺序与日志说明。
- 失败回滚：
  - 将约束校验置于最终输出前的“硬截断层”，先保正确性。
  - 暂停启用新评分权重，优先确保边界不越线。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/services -k "delta_max or tau or kl"
```

### AT-06 cloud 接口契约补强
- 目标：固化 `cloud_points/cloud_summary/uncertainty_band/cold_start_proxy` 字段语义。
- 输入：`/stats/prompt-time-density/cloud` 响应。
- 输出：API 合约测试、参数错误测试。
- 依赖：
  - 前置：无。
  - 并行可行：可与 AT-03/04/05 同时推进。
  - 后继影响：发布检查清单中的 API 稳定性项。
- DoD：
  - 正常请求字段齐全、类型稳定、空值策略明确。
  - `keyword` 缺失/参数越界返回 `422 + INVALID_INPUT`。
  - 错误码与错误 envelope 符合项目既有约定。
- 失败回滚：
  - 新增字段可临时降为可选，但不得删除既有字段。
  - 参数校验异常时回滚到“保守校验集”，确保 4xx 不误伤正常流量。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/core_business/test_api_group_b_core_contract.py
```

### AT-07 决策日志完整性校验
- 目标：保证每次 priority 计算可追踪 `request_id/chosen_window/is_chosen` 及核心概率字段。
- 输入：`_persist_policy_decision_logs(...)`；`PromptTimePolicyDecisionLog`。
- 输出：集成测试（或最小可行仓内校验）验证日志完整性。
- 依赖：
  - 前置：AT-01/02/03 完成（字段语义与契约先稳定）。
  - 并行可行：可与 AT-08 前期脚手架并行，但入库字段校验需先完成。
  - 后继影响：AT-08 OPE 数据可用性。
- DoD：
  - 日志记录包含：`noun_group_id/vector_overlap/shift_signal/p_base/p_new/kl_to_base`。
  - 日志写入失败时，主请求策略可配置（失败即失败或降级告警）。
  - 测试覆盖 DB session mock/测试库两种模式之一且可重复。
- 失败回滚：
  - 降级为“异步补偿写日志”并记录缺失率指标。
  - 严重故障时关闭新字段写入，仅保留关键追踪字段不中断主流程。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/integration -k "policy_decision_log and priority"
```

### AT-08 OPE 离线评估脚本
- 目标：提供最小 OPE 脚本，支持 Replay、IPS、SNIPS、DR。
- 输入：`prompt_time_policy_decision_logs` + `prompt_time_window_feedback`。
- 输出：按 `policy_version` 产出离线评估报告（JSON/Markdown）。
- 依赖：
  - 前置：AT-07（日志字段完整）。
  - 并行可行：可先完成脚本骨架与 CLI 解析，待日志落地后联调。
  - 后继影响：AT-09 发布门禁阈值。
- DoD：
  - 支持时间窗过滤、policy_version 过滤、样本量统计。
  - 输出包含指标值、置信区间/稳定性提示、数据覆盖率。
  - dry-run 与真实数据模式均可运行。
- 失败回滚：
  - 指标不可用时输出“不可判定”并阻断自动放行。
  - 临时回退到 Replay-only 模式，但必须在报告中显式标记降级。
- 最小验证命令：
```bash
cd main/backend && python3.11 scripts/ope/run_ope_eval.py \
  --policy-version v_next --since 2026-03-01 --until 2026-03-14 --dry-run
```

### AT-09 Go/No-Go 接入 OPE 指标
- 目标：把 OPE 结果并入发布门禁，不再仅依赖在线即时指标。
- 输入：现有 Go/No-Go 脚本与报告结构；AT-08 报告。
- 输出：新增 OPE 阈值检查（>=1 组 hard threshold + >=1 组 warning）。
- 依赖：
  - 前置：AT-08 完成且报告结构稳定。
  - 并行可行：可与 AT-10 局部并行（配置结构定义）。
  - 后继影响：发布检查清单最终放行判定。
- DoD：
  - OPE 文件缺失、样本不足、指标低于 hard threshold 时门禁失败。
  - warning 阈值触发时可继续但必须输出显式告警。
  - 门禁脚本具备失败样例回归测试。
- 失败回滚：
  - 若 OPE 计算链路故障，发布流程切换到“人工审批 + 风险声明”临时通道。
  - 临时通道必须有有效期，到期恢复自动硬门禁。
- 最小验证命令：
```bash
cd main/backend && bash scripts/release/go_no_go.sh --with-ope --check-only
```

### AT-10 策略版本化参数配置
- 目标：将 `a:b:c:d`、`eta/delta_max/tau/min_overlap/target_overlap` 外置并按 `policy_version` 管理。
- 输入：priority 函数硬编码参数。
- 输出：策略配置结构、加载器、版本切换机制。
- 依赖：
  - 前置：AT-01/05 指标与边界口径明确。
  - 并行可行：可与 AT-02/09 并行。
  - 后继影响：配置治理、发布检查中的参数审计项。
- DoD：
  - 不改代码仅切换 `policy_version` 即可变更参数组合。
  - 参数 schema 校验通过（类型、区间、必填）。
  - 缺失版本时有默认回退策略与告警。
- 失败回滚：
  - 保留最后一个“已验证版本”作为兜底（如 `policy_version=stable`）。
  - 新版本加载失败自动回退 `stable` 并拒绝静默继续。
- 最小验证命令：
```bash
cd main/backend && python3.11 -m pytest -q \
  tests/services -k "policy_version and config and priority"
```

## 2. 里程碑与并行调度

### M1：策略与契约基线固化（T+0 ~ T+2）
- 范围：AT-01、AT-02、AT-03、AT-06、AT-10(骨架)。
- 里程碑出口：
  - `target_overlap` 生效；
  - priority/cloud 核心契约通过；
  - `policy_version` 配置加载可跑通。

### M2：约束正确性与可观测性闭环（T+2 ~ T+4）
- 范围：AT-04、AT-05、AT-07。
- 里程碑出口：
  - 退化路径与约束边界测试稳定；
  - 决策日志关键字段完整可追踪。

### M3：离线评估接入发布门禁（T+4 ~ T+6）
- 范围：AT-08、AT-09、AT-10(收口)。
- 里程碑出口：
  - OPE 报告稳定产出；
  - Go/No-Go 纳入 OPE hard/warn 双阈值；
  - 配置治理与发布清单可执行。

### 并行调度图（文本版）
```text
Phase A (并行)
  [AT-01] [AT-02] [AT-03] [AT-06] [AT-10(骨架)]
      |       |       |       |         |
      +-------+---+---+-------+---------+
                  v
Phase B (并行)
           [AT-04] [AT-05] [AT-07]
               |      |       |
               +------+---+---+
                          v
Phase C (串行主链)
                 [AT-08] -> [AT-09]
                          \
                           -> [AT-10(收口与参数审计)]
```

## 3. 风险登记册（Risk Register）

| 风险ID | 风险描述 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|---|
| R1 | `target_overlap` 引入后排序抖动超预期，影响线上稳定性 | 中 | 高 | 灰度开关 + 对照组监控 + `stable` 参数回退 |
| R2 | O1 provider 不稳定导致 overlap 估计超时 | 中 | 中 | provider 超时熔断 + 启发式自动回退 + 失败率告警 |
| R3 | 契约补强后历史调用方因字段/类型不一致失败 | 低 | 高 | 先在 CI 与预发跑全量契约，必要时保留兼容字段窗口 |
| R4 | `delta_max/tau` 约束与新评分项冲突，出现不可行解 | 中 | 高 | 增加“硬截断层”与冲突优先级，确保输出始终有界 |
| R5 | 决策日志缺失导致 OPE 样本不可用 | 中 | 高 | AT-07 先行，日志完整性日检 + 缺失率阈值告警 |
| R6 | OPE 数据样本不足导致门禁误判 | 中 | 中 | 增加样本量下限；不足时阻断自动放行并触发人工审批 |
| R7 | 参数外置后配置漂移（环境不一致） | 中 | 中 | 配置 schema 校验 + 配置签名/版本锁 + 发布前 diff 审核 |
| R8 | 发布门禁新增 OPE 后影响发布时效 | 低 | 中 | 门禁脚本分层执行（快速检查/完整检查）+ 缓存最近评估结果 |

## 4. 配置治理

### 4.1 配置分层
- 运行时层：`policy_version` 选择与只读参数加载。
- 版本层：每个策略版本一组完整参数（含 `a:b:c:d`、`eta/delta_max/tau/min_overlap/target_overlap`）。
- 治理层：schema、审计、变更记录、回滚指针（`stable`）。

### 4.2 配置规则
- 所有参数必须通过 schema 校验（类型、范围、默认值、必填）。
- `policy_version` 不允许覆盖写；仅允许新增版本并切换指针。
- 参数变更必须附带：
  - 变更原因；
  - 影响评估（至少包含 `p_new` 分布变化预估）；
  - 回滚版本号。
- 生产环境禁止手工临时改参数文件；必须走版本化发布。

### 4.3 审计与回滚
- 每次读取策略参数写入日志：`policy_version`、配置哈希、请求时间窗。
- 发现异常时优先回滚到 `stable`，并冻结新版本继续放量。
- 保留最近 N 个版本（建议 N>=5）以支持追溯。

## 5. 发布检查清单（Release Checklist）

### 5.1 代码与测试
- [ ] AT-01~AT-10 对应代码/脚本均已合入候选分支。
- [ ] 核心契约测试通过：
```bash
cd main/backend && python3.11 -m pytest -q tests/core_business/test_process_consistency_core_contract.py
cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py
```
- [ ] 关键服务层与集成测试通过（overlap/约束/日志/OPE/门禁）。

### 5.2 数据与评估
- [ ] OPE 报告存在且时间窗正确，样本量达到下限。
- [ ] Replay、IPS、SNIPS、DR 指标均已产出；缺失项有明确原因。
- [ ] OPE hard threshold 全部通过；warning 项已评估并记录。

### 5.3 配置与可观测
- [ ] `policy_version` 已锁定并记录配置哈希。
- [ ] `stable` 回滚指针有效且已演练一次。
- [ ] 线上监控项就绪：`p_new-p_base` 分布、KL 分布、provider 回退率、日志缺失率。

### 5.4 Go/No-Go 决策
- [ ] Go/No-Go 脚本已执行并留档：
```bash
cd main/backend && bash scripts/release/go_no_go.sh --with-ope
```
- [ ] 若触发人工审批通道，已附风险声明、临时措施和失效日期。
- [ ] 发布后 24 小时回看计划已安排（指标与日志抽样）。

## 6. 最小回归验证集合（建议执行顺序）

```bash
cd main/backend
python3.11 -m pytest -q tests/core_business/test_process_consistency_core_contract.py
python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py
python3.11 -m pytest -q tests/services -k "overlap or avoid_peak or delta_max or tau or policy_version"
python3.11 -m pytest -q tests/integration -k "policy_decision_log and priority"
python3.11 scripts/ope/run_ope_eval.py --policy-version v_next --since 2026-03-01 --until 2026-03-14 --dry-run
bash scripts/release/go_no_go.sh --with-ope --check-only
```

---
以上内容即为本目录当前执行口径，按里程碑和门禁顺序推进即可落地。
