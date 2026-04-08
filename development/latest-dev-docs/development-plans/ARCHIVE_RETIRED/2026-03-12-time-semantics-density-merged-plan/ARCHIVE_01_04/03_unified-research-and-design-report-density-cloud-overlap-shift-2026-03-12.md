# 统一研究与设计报告：时间名词密度云、重合约束与轻避峰分布改写（2026-03-12）

## 0. 文档目的

本报告将以下内容整合为一份一致口径文档：
- 现有主计划（时间语义 + noun_group 密度能力）
- 多轮论文与代码库调研结论
- 轻避峰策略的工程化落地规范

本报告作为该主题的统一设计入口；原文档保留，不删除。

## 1. 问题定义与边界

### 1.1 目标

在 `keyword_history_rag × time_window` 框架下，为新检索关键词生成更稳健的搜索参数分布：
- 语义相关性优先（由 `vector_overlap` 约束）
- 避峰为软约束（轻微重分布，而非硬错峰）
- 可解释、可回放、可回滚

### 1.2 非目标

- 不把避峰等同于去重。
- 不追求“彻底避开高峰窗口”。
- 不在 V1 强制引入高成本多向量在线 overlap 计算。

## 2. 一致化核心结论（基于参考资料）

1. `shift` 与 `避峰` 是两层机制：
- `shift` 负责语义中心修正（Rocchio/Dense-PRF/HyDE）。
- 避峰负责采样分布微调（受 overlap 与 KL 预算约束）。

2. 避峰策略采用“有界分布改写”，而非 `argmin` 式硬最小化：
- 通过 `eta` 控制偏移强度。
- 通过 `delta_max` 与 `tau`（KL 预算）限制偏移幅度。

3. 离线验证必须是反事实协议，不是只看在线样本均值：
- Replay + IPS/SNIPS + DR/Switch-DR/DRos。
- 使用统一 OPE 框架做可证伪评估。

4. 密度必须双层定义：
- `observed_density`（观测）
- `latent_density`（由失败率/重复率/覆盖率反推）

## 3. 统一架构与数据流

### 3.1 处理流程

1. 生成候选窗口：`keyword_history_rag × time_window`
2. 计算或读取 `q_shift`（可选）
3. 计算窗口 overlap，施加 `vector_overlap >= min_overlap`
4. 计算 `shift_signal`
5. 在 `p_base` 上做有界重分布得到 `p_new`
6. 输出窗口推荐、概率与决策 trace

### 3.2 模块职责

- `VectorShiftProvider`：`rocchio|dense_prf|hyde`
- `OverlapEstimator`：`O1/O2/O3` overlap 计算与版本化
- `DensityCloudBuilder`：密度云、峰谷、置信区间
- `WindowRedistributor`：`p_base -> p_new`（受 `delta_max/tau` 约束）
- `PolicyEvaluator`：OPE 离线评估与门禁

## 4. 算法定义（统一版本）

### 4.1 overlap

- `O1`: `cos(e(query), e(window_centroid))`（V1线上）
- `O2`: `maxsim(E_query, E_window_docs)`（离线对照）
- `O3`: `cos(e(noun_group_id), e(window_repr_task))`（任务条件化）

V1 规定：线上使用 `O1`，离线并行记录 `O2/O3`。

### 4.2 潜在密度

- `observed_density = effective_new_docs / window_days`
- `latent_density_score = observed_density * (1-dup_ratio)^u * (1-fail_rate)^v * coverage^w`

### 4.3 轻避峰重分布

- `shift_signal = a*peak_pressure + b*(1-latent_density) + c*(1-overlap) + d*freshness_cost`
- `p_new(w) ∝ p_base(w) * exp(-eta * shift_signal(w))`
- 约束：
  - `|p_new(w)-p_base(w)| <= delta_max`
  - `KL(p_new || p_base) <= tau`

说明：避峰是“分布微调”，不是“去重动作”。

## 5. 参数契约（V1 默认）

- `min_overlap = 0.35`
- `target_overlap = 0.55`
- `eta = 0.08`
- `delta_max = 0.12`
- `tau = 0.03`
- `peak_percentile = 0.85`
- `explore_rate = 0.08`
- 权重：`a:b:c:d = 0.40:0.20:0.25:0.15`
- 反推权重：`u:v:w = 0.40:0.35:0.25`

参数变更要求：
- 必须绑定 `policy_version`。
- 必须附带离线 OPE 报告与 canary 结果。

## 6. 数据契约（落库实体）

- `window_density_stats`
- `window_collection_feedback`
- `window_embedding_profile`
- `noun_group_overlap_cache`
- `shift_experiment_log`
- `policy_decision_log`

`policy_decision_log` 最低字段：
- `shift_signal_breakdown`
- `p_base`
- `p_new`
- `kl_to_base`
- `policy_version`

## 7. API 一致口径

`GET /api/v1/stats/prompt-time-density/priority`：
- 入参新增：`eta`, `delta_max`, `tau`
- 出参新增：`shift_signal`, `p_base`, `p_new`, `kl_to_base`

退化规则：
- `avoid_peak=false` 时，返回 `p_new == p_base`（或仅保留探索噪声差异）。

## 8. 评估与门禁（可证伪闭环）

### 8.1 离线 OPE 评估

必须同时输出：
- Replay
- IPS / SNIPS
- DR / Switch-DR / DRos

### 8.2 在线门禁

- `overlap_pass_rate`
- `effective_new_docs_rate`
- `dup_ratio`
- `fail_rate`
- `KL(p_new||p_base)` P95
- `max |p_new-p_base|`

回滚条件：
- 连续 48 小时核心指标恶化，回退上一个 `policy_version`。

## 9. 风险与缓解

1. 过严 overlap 导致可行窗口塌缩
- 缓解：`feasible_window_count` 下限 + 自动降门槛。

2. 基础设施故障污染反馈
- 缓解：`infra_fail` 与 `retrieval_fail` 分离打标。

3. 冷启动抖动
- 缓解：`cold_start_proxy` + 小流量探索 + 分布偏移预算。

4. shift 语义漂移
- 缓解：A/B 比较 `no-shift` 对照，要求收益稳定再扩容。

## 10. 实施优先级

1. 先完成 API/数据契约与决策 trace。
2. 接入 bounded redistribution（`eta/delta_max/tau`）。
3. 接入 OPE 离线评估流水线。
4. 再逐步提高 shift 覆盖率（`dense_prf -> hyde`）。

## 11. 参考资料（重点）

### 11.1 论文与文档（在线）

- TRPO (PMLR 2015): https://proceedings.mlr.press/v37/schulman15.html
- CPO (arXiv 2017): https://arxiv.org/abs/1705.10528
- OBP / Open Bandit Dataset (arXiv 2021): https://arxiv.org/abs/2008.07146
- DRos (ICML 2020): https://proceedings.mlr.press/v119/su20a.html
- HyDE (arXiv 2022): https://arxiv.org/abs/2212.10496
- OPRF (SIGIR 2023): https://arxiv.org/abs/2308.10191
- ColBERT-PRF (ICTIR 2021): https://arxiv.org/abs/2106.11251

### 11.2 本地已下载论文

目录：`references/papers_round3/`
- `2015_TRPO_Schulman.pdf`
- `2017_CPO_Achiam.pdf`
- `2020_DRos_Su.pdf`
- `2021_OBP_Saito.pdf`

### 11.3 本地已爬代码库（核心）

目录：`references/repos/`
- `zr-obp`（OPE 框架与样例）
- `ULTRA`（去偏 LTR）
- `DualIPW`（偏置稳健训练）
- `MULTR`（长尾稳健 ULTR）
- `OPRF`（Dense PRF）
- `hyde`（生成式 query shift）
- `pyterrier_colbert`（ColBERT-PRF）
- `cpo`, `spinningup`, `sb3_contrib`（受约束策略更新实现参考）

## 12. 与原文关系

- 原文档保留：
  - `01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md`
  - `02_research-report-density-cloud-overlap-avoid-peak-2026-03-12.md`
- 本文档为一致版总报告，后续评审与实现以本文优先。

## 13. 一致性核对（逐节“参考+实现”映射）

| 报告章节 | 论文/资料来源 | 来源实现参考（本地） | 覆盖状态 |
|---|---|---|---|
| 1. 问题定义与边界 | HyDE, OPRF, ColBERT-PRF（检索语义层） | `references/repos/hyde/src/hyde/hyde.py`, `references/repos/OPRF/source/search.py`, `references/repos/pyterrier_colbert/README.md` | OK |
| 2. 一致化核心结论 | TRPO, CPO, OBP, DRos | `references/repos/cpo/optimizers/conjugate_constraint_optimizer.py`, `references/repos/zr-obp/examples/multiclass/evaluate_off_policy_estimators.py` | OK |
| 3. 架构与数据流 | OBP/ULTRA（评估与去偏流水线） | `references/repos/zr-obp/examples/replay/evaluate_off_policy_estimators.py`, `references/repos/ULTRA/ultra/learning_algorithm/ipw_rank.py` | OK |
| 4. 算法定义 | TRPO/CPO（KL 约束思想）, DR/DRos（评估）, HyDE/OPRF/ColBERT-PRF（shift） | `references/repos/spinningup/spinup/algos/tf1/trpo/trpo.py`, `references/repos/sb3_contrib/sb3_contrib/trpo/trpo.py`, `references/repos/anserini/src/main/java/io/anserini/rerank/lib/RocchioReranker.java` | OK |
| 5. 参数契约 | TRPO/CPO（步长与约束预算）, OBP（离线调参） | `references/repos/cpo/optimizers/conjugate_constraint_optimizer.py`, `references/repos/zr-obp/examples/multiclass/evaluate_off_policy_estimators.py` | OK |
| 6. 数据契约 | 现有系统统计链路 + OPE 日志要求 | `main/backend/app/services/stats/prompt_time_density.py`, `references/repos/zr-obp/examples/*` | OK |
| 7. API 一致口径 | 主计划工程约束 + OPE可回放要求 | `main/backend/app/services/stats/prompt_time_density.py`（现有基座）, `references/repos/zr-obp`（评估对接） | OK |
| 8. 评估与门禁 | OBP, DR, Switch-DR, DRos | `references/repos/zr-obp/examples/multiclass/evaluate_off_policy_estimators.py`, `references/repos/zr-obp/examples/synthetic/README.md` | OK |
| 9. 风险与缓解 | ULTRA, DualIPW, MULTR（偏置/长尾风险） | `references/repos/ULTRA/ultra/utils/propensity_estimator.py`, `references/repos/DualIPW/*`, `references/repos/MULTR/*` | OK |
| 10. 实施优先级 | 主计划阶段化落地 + 调研库可接入性 | `01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md`, `references/repos/*` | OK |
| 11. 参考资料 | 论文链接 + 本地 PDF + 本地仓库 | `references/papers_round3/*.pdf`, `references/repos/*` | OK |
| 12. 与原文关系 | 文档治理规范 | `01_...md`, `02_...md` | OK |

核对结论：
- 当前一致性报告每个章节均已补齐“研究参考 + 来源实现参考”。
- 若后续新增章节，必须先在本节追加对应映射再进入评审。

## 14. 本地项目实现接口章节（Local Integration Interface）

### 14.1 已实现接口（当前代码）

HTTP 路由：
1. `GET /api/v1/stats/prompt-time-density`
2. `GET /api/v1/stats/prompt-time-density/priority`
3. `GET /api/v1/stats/prompt-time-density/select-windows`

代码位置：
1. `main/backend/app/api/stats.py`
2. `main/backend/app/services/stats/prompt_time_density.py`
3. `main/backend/app/services/tasks.py`（`task_select_prompt_time_windows`）

当前服务函数：
1. `query_prompt_time_density`
2. `query_prompt_time_density_priority`
3. `select_priority_windows`

### 14.2 对齐本报告的目标接口（增量）

新增路由：
1. `GET /api/v1/stats/prompt-time-density/cloud`

扩展路由（priority）：
1. 新增入参：`min_overlap`, `target_overlap`, `eta`, `delta_max`, `tau`, `avoid_peak`
2. 新增出参：`vector_overlap`, `shift_signal`, `p_base`, `p_new`, `kl_to_base`, `offpeak_confidence`
3. 命名迁移：`prompt_group_id -> noun_group_id`（兼容期双字段）

新增服务函数建议：
1. `query_prompt_time_density_cloud`
2. `estimate_window_overlap`
3. `redistribute_window_probabilities`
4. `policy_decision_trace`

### 14.3 任务接口对齐（Celery）

现有任务：
1. `task_select_prompt_time_windows(...)`（`main/backend/app/services/tasks.py`）

扩展建议：
1. 任务入参增加 `eta/delta_max/tau/min_overlap`
2. 任务返回增加 `p_base/p_new/kl_to_base`
3. 任务日志写入 `policy_decision_log`
