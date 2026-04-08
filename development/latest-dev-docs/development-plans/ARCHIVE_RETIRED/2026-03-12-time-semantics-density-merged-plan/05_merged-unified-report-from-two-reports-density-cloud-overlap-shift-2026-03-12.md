# 时间语义与密度能力：01×05 完整合并主报告（单文档可开工版，2026-03-12）

## 0. 文档定位与合并原则

本报告用于将以下内容合并为唯一研发入口：
1. `01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md`（执行骨架）
2. `04_backend-interface-change-checklist-density-cloud-overlap-shift-2026-03-12.md`（接口改造清单）
3. `05_merged-unified-report-from-two-reports-density-cloud-overlap-shift-2026-03-12.md` 既有内容（调研与实现细节）

合并原则：
1. 章节框架采用 `01` 的结构（`0~9`）。
2. 内容细节采用 `05` 的完整度（算法、接口、数据契约、评估、参考实现），并完整吸收 `04` 的接口改造清单。
3. 原文档全部保留，不删除。
4. 本文档作为“只看一份即可开发”的主报告。

## 1. 当前状态调查结论（截至 2026-03-12）

### 1.1 已有基线能力

1. 后端已有时间密度与优先级接口：
- `GET /api/v1/stats/prompt-time-density`
- `GET /api/v1/stats/prompt-time-density/priority`
- `GET /api/v1/stats/prompt-time-density/select-windows`

2. 已有服务基座：
- `main/backend/app/services/stats/prompt_time_density.py`
- `main/backend/app/services/tasks.py`（`task_select_prompt_time_windows`）

3. 已有 realcase 与 Go/No-Go 脚本，可复用门禁链路。

### 1.2 当前主要缺口

1. 语义层与调度层耦合不足：`shift`、`overlap`、`off-peak` 未形成统一决策链。
2. 缺少 `density_cloud` 接口与可回放决策 trace。
3. 反事实评估（OPE）尚未成为发布前强制门禁。
4. 命名仍存在 `prompt_group_id` 与 `noun_group_id` 并轨风险。

## 2. 合并后统一目标

### 2.1 统一业务目标

1. 在 `keyword_history_rag × time_window` 体系下输出稳定采样分布。
2. 语义相关性优先，避峰为软约束。
3. 避峰与去重分层，避免目标混淆。
4. 冷启动可运行，可解释，可回滚。

### 2.2 统一技术目标

1. 策略采用“有界分布改写”（非硬最小化）。
2. 引入 `vector_overlap` 门控与 `shift_signal` 排序信号。
3. 引入 `p_base/p_new/kl_to_base` 全链路可观测。
4. 引入 OPE（Replay + IPS/SNIPS + DR/Switch-DR/DRos）作为离线强制评估。

## 3. 统一术语与字段字典

### 3.1 核心术语

1. `noun_group_id`：统一语义组主键。
2. `density_cloud`：时间轴密度云（峰/谷/置信区间）。
3. `observed_density`：观测密度。
4. `latent_density_score`：由失败/重复/覆盖反推的潜在密度。
5. `vector_overlap`：语义重合度。
6. `shift_signal`：调度信号。
7. `p_base`, `p_new`：改写前后窗口分布。
8. `kl_to_base`：改写后相对基线分布的 KL 距离。

### 3.2 命名兼容策略

1. 入参兼容：`prompt_group_ids[]` -> 归一为 `noun_group_ids[]`。
2. 出参兼容：过渡期同时返回 `prompt_group_id` 与 `noun_group_id`。
3. 前端 query key 与图表维度逐步统一为 `noun_group_id`。

## 4. 统一 API 契约（主口径）

### 4.1 已有接口（当前代码）

1. `GET /api/v1/stats/prompt-time-density`
2. `GET /api/v1/stats/prompt-time-density/priority`
3. `GET /api/v1/stats/prompt-time-density/select-windows`

代码位置：
1. `main/backend/app/api/stats.py`
2. `main/backend/app/services/stats/prompt_time_density.py`
3. `main/backend/app/services/tasks.py`

### 4.2 新增接口：密度云

`GET /api/v1/stats/prompt-time-density/cloud`

请求参数：
1. `keyword`（required）
2. `time_window | start+end`
3. `bucket`
4. `source_domains[]`
5. `noun_group_ids[]`（兼容 `prompt_group_ids[]`）
6. `smoothing=ema|gaussian|none`
7. `peak_percentile`
8. `uncertainty`

返回字段：
1. `cloud_points[]`
2. `cloud_summary`
3. `uncertainty_band`
4. `cold_start_proxy`（可选）

### 4.3 扩展接口：priority

`GET /api/v1/stats/prompt-time-density/priority`

新增请求参数：
1. `min_overlap`
2. `target_overlap`
3. `eta`
4. `delta_max`
5. `tau`
6. `avoid_peak`

新增返回字段：
1. `vector_overlap`
2. `shift_signal`
3. `p_base`
4. `p_new`
5. `kl_to_base`
6. `offpeak_confidence`

退化规则：
1. `avoid_peak=false` 时，`p_new == p_base`（探索噪声除外）。

### 4.4 算法与策略定义

#### 4.4.1 overlap

1. `O1 = cos(e(query), e(window_centroid))`（V1线上）
2. `O2 = maxsim(E_query, E_window_docs)`（离线）
3. `O3 = cos(e(noun_group_id), e(window_repr_task))`（离线）

V1：线上 O1，离线并行 O2/O3。

#### 4.4.2 潜在密度

1. `observed_density = effective_new_docs / window_days`
2. `latent_density_score = observed_density * (1-dup_ratio)^u * (1-fail_rate)^v * coverage^w`

#### 4.4.3 轻避峰分布改写

1. `shift_signal = a*peak_pressure + b*(1-latent_density) + c*(1-overlap) + d*freshness_cost`
2. `p_new(w) ∝ p_base(w) * exp(-eta * shift_signal(w))`
3. `|p_new(w)-p_base(w)| <= delta_max`
4. `KL(p_new||p_base) <= tau`

#### 4.4.4 在线伪代码

```text
input: candidate_windows, p_base, overlap, peak_pressure, latent_density
feasible = {w | overlap(w) >= min_overlap}
if feasible is empty: return cold_start_proxy
for w in feasible:
  shift_signal(w) = a*peak_pressure + b*(1-latent_density) + c*(1-overlap) + d*freshness_cost
  raw(w) = p_base(w) * exp(-eta*shift_signal(w))
p_new = normalize(raw)
p_new = clip_per_window(p_new, p_base, delta_max)
if KL(p_new || p_base) > tau: p_new = project_to_kl_budget(p_new, p_base, tau)
return sample_or_rank_by(p_new)
```

### 4.5 参数默认值与分期

#### 4.5.1 统一默认值（V1）

1. `min_overlap=0.35`, `target_overlap=0.55`
2. `eta=0.08`, `delta_max=0.12`, `tau=0.03`
3. `peak_percentile=0.85`, `explore_rate=0.08`
4. `a:b:c:d = 0.40:0.20:0.25:0.15`
5. `u:v:w = 0.40:0.35:0.25`

#### 4.5.2 冷启动期（前 7-14 天）

1. `min_overlap=0.30~0.35`
2. `target_overlap=0.50~0.55`
3. `explore_rate=0.15~0.25`
4. `u:v:w = 0.35:0.45:0.20`

#### 4.5.3 稳定期

1. `min_overlap=0.35~0.45`
2. `target_overlap=0.55~0.70`
3. `explore_rate=0.05~0.12`
4. `u:v:w = 0.40:0.35:0.25`

### 4.6 数据契约（落库实体）

1. `window_density_stats`
2. `window_collection_feedback`
3. `window_embedding_profile`
4. `noun_group_overlap_cache`
5. `shift_experiment_log`
6. `policy_decision_log`

`policy_decision_log` 最低字段：
1. `features_json`
2. `shift_signal_breakdown`
3. `p_base`, `p_new`, `kl_to_base`
4. `chosen_window`
5. `policy_version`

### 4.7 服务层改造清单（函数级）

本节来源：`04_backend-interface-change-checklist-density-cloud-overlap-shift-2026-03-12.md` 已完整并入。

文件：`main/backend/app/services/stats/prompt_time_density.py`

新增：
1. `query_prompt_time_density_cloud(...)`
2. `estimate_window_overlap(...)`
3. `redistribute_window_probabilities(...)`
4. `build_policy_decision_trace(...)`

改造：
1. `query_prompt_time_density_priority(...)`
2. `select_priority_windows(...)`

文件：`main/backend/app/services/tasks.py`

任务扩展：`task_select_prompt_time_windows(...)`

新增入参：
1. `eta`, `delta_max`, `tau`
2. `min_overlap`, `target_overlap`
3. `avoid_peak`

新增回传：
1. `p_base`, `p_new`, `kl_to_base`
2. `offpeak_confidence`

### 4.8 错误契约

1. 参数非法统一 `422 + INVALID_INPUT`。
2. 关键范围校验：
- `eta >= 0`
- `0 <= delta_max <= 1`
- `tau >= 0`
- `0 <= min_overlap <= 1`

## 5. 执行路线（主线 + 演进）

### 5.1 Phase R（Remediation）

1. 巩固现有密度接口与 realcase 口径。
2. 补齐对账与 Go/No-Go 自动化。

### 5.2 Phase S（Semantics）

1. `prompt_group_id -> noun_group_id` 兼容迁移。
2. 前后端参数统一。

### 5.3 Phase C（Cloud）

1. 上线 `cloud` 接口。
2. 上线 overlap gate。
3. 上线 bounded redistribution。
4. 接入 `policy_decision_log`。
5. 接入离线 OPE 流水线。

### 5.4 Phase D（Decoupled）

1. `Timestamp Resolver` 独立化。
2. `Noun Density Aggregator` 独立化。
3. 主 ingest 链路保留编排。

### 5.5 原子执行顺序

1. API schema 与兼容层
2. cloud 查询与 overlap 估计
3. bounded redistribution
4. Celery 任务扩展
5. OPE + 门禁 + 回滚

## 6. 最小验证集合（统一门禁）

### 6.1 单元测试

1. 云构建（峰谷/平滑/突发）
2. overlap 门控
3. `delta_max/tau` 约束
4. `avoid_peak=false` 退化一致性

### 6.2 API 合约测试

1. `/stats/prompt-time-density/cloud`
2. `/stats/prompt-time-density/priority` 新参数/新字段
3. 错误参数返回 `422`

### 6.3 集成测试

1. Celery 参数贯通
2. `policy_decision_log` 完整写入
3. `noun_group_id` 兼容路径

### 6.4 现有可复用命令

1. 后端契约：
`cd main/backend && python3.11 -m pytest -q tests/core_business/test_api_group_b_core_contract.py tests/core_business/test_admin_dashboard_process_core_contract.py tests/core_business/test_process_consistency_core_contract.py`

2. realcase：
`cd main/backend && python3.11 scripts/run_realcase_prompt_time_density.py --project demo_proj --case-set all --fail-fast`

3. 前端 modern：
`cd main/frontend-modern && npm run -s lint && npm run -s test -- GraphPage`

4. Go/No-Go：
`cd main/backend && python3.11 scripts/generate_prompt_time_density_gonogo.py --realcase .artifacts/realcase_prompt_time_density_report.json --perf .artifacts/perf_metrics.json --output .artifacts/prompt_time_density_gonogo.md`

### 6.5 发布门禁

1. `KL(p_new||p_base)` P95 `<= tau`
2. `max |p_new-p_base| <= delta_max`
3. `overlap_pass_rate` 不低于基线
4. `effective_new_docs_rate` 不劣化
5. 连续 48h 恶化触发回滚

## 7. 风险与处置

1. overlap 过严导致可行窗口塌缩
- 处置：`feasible_window_count` 下限 + 自动降门槛

2. 反馈污染
- 处置：`infra_fail` 与 `retrieval_fail` 分离

3. 冷启动抖动
- 处置：`cold_start_proxy + explore_rate + KL预算`

4. shift drift
- 处置：`no-shift` 对照 A/B

5. 平滑误判“假低谷”
- 处置：`offpeak_confidence + uncertainty_band + burst 分离字段`

## 8. 与原文档关系说明

原文保留：
1. `01_merged-remediation-and-smart-timestamp-plan-2026-03-12.md`
2. `02_research-report-density-cloud-overlap-avoid-peak-2026-03-12.md`
3. `03_unified-research-and-design-report-density-cloud-overlap-shift-2026-03-12.md`
4. `04_backend-interface-change-checklist-density-cloud-overlap-shift-2026-03-12.md`

主入口声明：
1. 本文档为当前主题唯一开发主报告。
2. 需求变更先更新本文，再回写补充文档。

### 8.1 本地证据映射（研究 + 实现）

| 模块 | 研究参考 | 来源实现参考（本地） |
|---|---|---|
| Shift | HyDE / OPRF / ColBERT-PRF | `references/repos/hyde/src/hyde/hyde.py`, `references/repos/OPRF/source/search.py`, `references/repos/pyterrier_colbert/README.md`, `references/repos/anserini/src/main/java/io/anserini/rerank/lib/RocchioReranker.java`, `references/repos/anserini/src/main/java/io/anserini/rerank/lib/Rm3Reranker.java` |
| 受约束改分布 | TRPO / CPO | `references/repos/spinningup/spinup/algos/tf1/trpo/trpo.py`, `references/repos/sb3_contrib/sb3_contrib/trpo/trpo.py`, `references/repos/cpo/optimizers/conjugate_constraint_optimizer.py` |
| OPE 评估 | OBP / DR / Switch-DR / DRos | `references/repos/zr-obp/examples/multiclass/evaluate_off_policy_estimators.py`, `references/repos/zr-obp/examples/replay/evaluate_off_policy_estimators.py`, `references/repos/zr-obp/examples/synthetic/README.md` |
| 去偏与长尾稳健 | ULTRA / DualIPW / MULTR | `references/repos/ULTRA/ultra/utils/propensity_estimator.py`, `references/repos/ULTRA/ultra/learning_algorithm/ipw_rank.py`, `references/repos/DualIPW/*`, `references/repos/MULTR/*` |
| 本地基座 | 后端统计与任务 | `main/backend/app/api/stats.py`, `main/backend/app/services/stats/prompt_time_density.py`, `main/backend/app/services/tasks.py` |

### 8.2 参考资料（完整）

在线：
1. TRPO: https://proceedings.mlr.press/v37/schulman15.html
2. CPO: https://arxiv.org/abs/1705.10528
3. OBP/OBD: https://arxiv.org/abs/2008.07146
4. DRos: https://proceedings.mlr.press/v119/su20a.html
5. DR 基础: https://arxiv.org/abs/1503.02834
6. Switch-DR: https://arxiv.org/abs/1612.01205
7. HyDE: https://arxiv.org/abs/2212.10496
8. OPRF: https://arxiv.org/abs/2308.10191
9. ColBERT-PRF: https://arxiv.org/abs/2106.11251
10. MULTR: https://arxiv.org/pdf/2207.11785.pdf
11. MMR: https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf
12. xQuAD: https://ra.ethz.ch/cdstore/www2010/www/p881.pdf
13. Good-Turing: https://www.grsampson.net/AGtf1.html
14. Chao: https://www.jstor.org/stable/2531532

本地论文：`references/papers_round3/`
1. `2015_TRPO_Schulman.pdf`
2. `2017_CPO_Achiam.pdf`
3. `2020_DRos_Su.pdf`
4. `2021_OBP_Saito.pdf`

本地仓库：`references/repos/`
- `anserini`, `pyserini`, `OPRF`, `hyde`, `pyterrier_colbert`, `pyterrier`
- `zr-obp`, `ULTRA`, `DualIPW`, `MULTR`, `Counterfactual-DR`
- `cpo`, `spinningup`, `sb3_contrib`
- `dense-screening-feedback`, `Group-QPP`, `recapr`, `Tempo`, `MA4DIV`, `pyversity`

## 9. 原任务映射（简版）

1. 执行骨架沿用 `01` 的 `Phase R/S/C/D`。
2. 研究细节由本报告 `4/6/8` 章补齐，替代多文档来回跳转。
3. 若拆原子任务，建议按以下 ID：
- `AT-01` API schema 与兼容层
- `AT-02` density cloud service + endpoint
- `AT-03` overlap estimator
- `AT-04` bounded redistribution core
- `AT-05` task_select_prompt_time_windows 扩展
- `AT-06` policy_decision_log 落库
- `AT-07` OPE offline pipeline
- `AT-08` unit/contract/integration tests
- `AT-09` canary + go/no-go + rollback
