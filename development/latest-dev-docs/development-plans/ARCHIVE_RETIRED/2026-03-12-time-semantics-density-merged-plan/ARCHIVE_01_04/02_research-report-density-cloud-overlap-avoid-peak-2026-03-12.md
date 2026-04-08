# 调查报告：时间名词密度云与重合约束避峰采集（2026-03-12）

## 1. 背景与目标

当前需求不是“彻底错开高峰窗口”，而是：

- 以 `keyword_history_rag × time_window` 构建 `density_cloud`；
- 在保证语义相关性的前提下执行避峰采集；
- 使用“可接受时间/名词向量重合度”约束调度分布，而非硬性错峰。

本报告目标：给出可落地的算法、工程路径与参数方案。

## 2. 调查范围与材料

### 2.1 本地论文（已下载）

- `1998_MMR_Carbonell_Goldstein.pdf`
- `2010_xQuAD_Explicit_Search_Result_Diversification.pdf`
- `2002_Bursty_Hierarchical_Structure_Kleinberg.pdf`
- `2010_Contextual_Bandit_News_Recommendation.pdf`
- `2010_Unbiased_Offline_Eval_Contextual_Bandit.pdf`
- `2025_TempRetriever_Time_Aware_Multi_Vector_Retrieval.pdf`

### 2.2 本地代码库（已克隆）

- 检索与召回：`pyserini`, `anserini`
- 多样化重排：`pyversity`, `MA4DIV`
- 在线探索利用：`contextualbandits`, `vowpal_wabbit`, `mabwiser`, `SMPyBandits`
- 时间检索评测参考：`Tempo`
- 向量 shift / 反馈重构补充：`OPRF`, `hyde`, `pyterrier_colbert`, `haystack`, `llama_index`
- 反推密度/评估补充：`pyterrier`, `Group-QPP`, `DenseRetrieval`, `Counterfactual-DR`, `dense-screening-feedback`, `recapr`

### 2.3 新增“向量 shift”代码证据（本地）

1. 词空间反馈重构（成熟实现）
- `anserini/src/main/java/io/anserini/rerank/lib/RocchioReranker.java`
  - 明确实现 `q_new = alpha*q + beta*pos - gamma*neg`
- `anserini/src/main/java/io/anserini/rerank/lib/Rm3Reranker.java`
  - 反馈模型与原 query 插值
- `anserini/src/main/java/io/anserini/rerank/lib/BM25PrfReranker.java`
  - PRF 扩展后二次检索

2. 稠密检索反馈与 embedding 级扩展
- `OPRF/README.md`
  - Offline Pseudo Relevance Feedback for single-pass dense retrieval
- `pyterrier_colbert/README.md`
  - 明确包含 ColBERT-PRF（多向量 PRF）
- `hyde/src/hyde/hyde.py`
  - HyDE 方案（生成假文档再编码检索）

3. 框架级可接入能力
- `haystack` 与 `llama_index` 可作为编排层接入 query transform/retrieval pipeline，但本身不是单一“shift 算法库”。

## 3. 核心结论

1. 主策略应为“两阶段”：
- 阶段 A（可行性约束）：`vector_overlap >= min_overlap`
- 阶段 B（可行集合内重排）：优先低峰值压力，同时控制重复率与新鲜度

2. 避峰是“软约束”而非“硬错峰”：
- 先保证相关性下限，再做峰值回避。
- 允许一定峰值窗口进入结果，避免语义有效性断崖下降。

3. 冷启动需引入探索机制：
- 纯历史密度云在新关键词上不稳定。
- 需小比例探索（bandit/replay 评估）持续修正分布。

4. 向量 shift 在业界是“有实现、可落地”的：
- 词空间：Rocchio/RM3/BM25-PRF（传统但稳定）
- 稠密空间：OPRF/ColBERT-PRF/HyDE（更贴近当前 RAG 检索）
- 与你的需求最匹配的是“shift + overlap约束 + 避峰重排”的组合，而不是单独替代时间窗策略。

## 4. 推荐算法方案

### 4.1 密度云构建

输入：`keyword_history_rag`, `time_window`, `bucket`, `source_domain`, `noun_group_id`。

输出：
- `cloud_points[]`: `{bucket_time, density, norm_density, zscore, is_peak, is_valley}`
- `cloud_summary`: `{p50, p75, p90, peak_ratio, valley_ratio, volatility, recommended_offpeak_windows[]}`
- `uncertainty_band`: `{lower, upper, method}`（可选）

峰谷识别建议：
- 基础：分位数阈值（如 `peak_percentile=0.85`）+ 平滑（EMA）
- 增强：突发检测（Kleinberg burst）用于异常峰期识别

### 4.2 重合约束避峰重排

约束：
- 硬门槛：`vector_overlap >= min_overlap`

重排目标：
- `shift_signal = a*peak_pressure_score + b*(1-latent_density_score) + c*(1-vector_overlap) + d*freshness_cost`
- 分布改写（轻避峰）：
  - `p_new(window) ∝ p_base(window) * exp(-eta * shift_signal(window))`
  - `|p_new - p_base| <= delta_max`（每窗口上限）
  - `KL(p_new || p_base) <= tau`（全局上限）

解释：
- `peak_pressure_score` 代表窗口拥挤程度；
- `vector_overlap` 以软惩罚进入目标，防止为避峰牺牲语义相关性。
- 避峰是“分布轻微重排”，不是“去重动作”；去重由独立 `dedup` 链路负责。

### 4.3 潜在密度反推（新增主模型）

问题定义：
- 来源信息密度是未知量，`effective_new_docs/window_days` 仅是观测值，不是潜在真实密度。

双层定义：
- `observed_density = effective_new_docs / window_days`
- `latent_density`：结合“失败率/重复率/覆盖率”反推得到的潜在信息密度

工程化反推公式（第一版）：
- `latent_density_score = observed_density * (1-dup_ratio)^u * (1-fail_rate)^v * coverage^w`

说明：
- `dup_ratio`：重复损失比例（越高，潜在新增越低）
- `fail_rate`：搜索失败 + 抓取失败 + 解析失败
- `coverage`：窗口采样覆盖度（窗口内有效尝试比例）

### 4.4 向量 shift 机制（新增）

定义：
- 对原始 query 向量 `q`，利用反馈样本或生成样本构造 `q_shift`，用于召回或重排。

可选实现：
1. Rocchio 风格（通用）
- `q_shift = alpha*q + beta*centroid(pos) - gamma*centroid(neg)`

2. Dense PRF 风格（OPRF / ColBERT-PRF）
- 从 top-k 伪相关结果提取 expansion embeddings，形成 `q_shift` 或 `q_expanded`。

3. HyDE 风格（生成式）
- 先生成“假设文档”，再编码为检索向量；等价于 query 语义中心迁移。

与错峰联动：
- 先用 `q_shift` 生成候选窗口相关性分数；
- 再施加 `vector_overlap >= min_overlap` 约束；
- 最后基于 `shift_signal` 做有界分布改写（轻避峰）。

### 4.5 冷启动策略

当目标 `noun_group_id` 数据不足时：
- 返回 `cold_start_proxy`（近邻 noun group 或 source 基线）；
- 附带 `offpeak_confidence`；
- 使用小比例探索流量更新真实回报（新增有效文档率、重复率）。

### 4.6 从论文到实现的映射（反推密度）

1. 经典反馈重排（Rocchio/RM3）
- 作用：修正 query 方向，降低无效检索窗口占比
- 本地证据：`anserini` 中 `RocchioReranker/Rm3Reranker/BM25PrfReranker`

2. Dense PRF（OPRF / ColBERT-PRF）
- 作用：从 top-k 伪相关样本提取扩展表示，提高 `observed_density` 的可用性
- 本地证据：`OPRF`、`pyterrier_colbert`

3. 失败率驱动在线修正（bandit）
- 作用：把失败/重复/收益转成反馈，动态调整窗口采样概率
- 本地证据：`contextualbandits`, `mabwiser`, `vowpal_wabbit`

## 5. 工程落地建议（面向当前仓库）

### 5.1 优先复用点

- 统计基座：`main/backend/app/services/stats/prompt_time_density.py`
- 调度基座：`main/backend/app/services/tasks.py`
- 采集链路：`main/backend/app/services/ingest/*`

### 5.2 新增模块建议

1. `DensityCloudBuilder`
- 负责 `keyword_history_rag × time_window` 聚合与云特征输出

2. `OverlapEstimator`
- 计算窗口候选与目标语义向量的 `vector_overlap`

3. `WindowReranker`
- 应用约束与评分函数输出推荐窗口

4. `CloudPolicy`（可选）
- 在线调整权重 `a,b,c,d` 与探索率

5. `VectorShiftProvider`（新增）
- 统一封装 `rocchio|dense_prf|hyde` 三类 shift 策略，输出 `q_shift` 与 `shift_confidence`

### 5.3 API 建议

- `GET /api/v1/stats/prompt-time-density/cloud`
- 扩展 `GET /api/v1/stats/prompt-time-density/priority` 参数：
  - `avoid_peak`
  - `max_peak_percentile`
  - `min_overlap`
  - `target_overlap`

## 6. 参数建议

### 6.1 冷启动期（前 7-14 天）

- `min_overlap = 0.30 ~ 0.35`
- `target_overlap = 0.50 ~ 0.55`
- `peak_percentile = 0.85`
- `u:v:w = 0.35:0.45:0.20`（先更重视失败率）
- 权重：`a:b:c:d = 0.35:0.20:0.30:0.15`
- `explore_rate = 0.15 ~ 0.25`

### 6.2 稳定期

- `min_overlap = 0.35 ~ 0.45`
- `target_overlap = 0.55 ~ 0.70`
- `peak_percentile = 0.80 ~ 0.90`
- `u:v:w = 0.40:0.35:0.25`（失败率与重复率平衡）
- 权重：`a:b:c:d = 0.40:0.20:0.25:0.15`
- `explore_rate = 0.05 ~ 0.12`

## 7. 观测指标与门禁

核心指标：
- `peak_window_share`
- `overlap_pass_rate`
- `effective_new_docs_rate`
- `dup_ratio`
- `fail_rate`
- `coverage`
- `latent_density_score`
- `offpeak_confidence`

门禁建议：
- `overlap_pass_rate < 70%` 告警
- `dup_ratio` 连续 3 天高于基线 20% 告警
- `peak_window_share` 不降反升触发策略回看

回滚条件：
- 连续 48 小时核心指标恶化，回退到“轻避峰 + overlap 下限”保守策略。

## 8. 实施优先级（建议）

1. 先实现 `cloud` 查询与 `priority` 扩展参数。
2. 接入 `min_overlap` 硬门槛与软惩罚评分。
3. 接入 `VectorShiftProvider`（先 `dense_prf`，后 `hyde`）。
4. 最后接入 bandit 在线调参与离线 replay 评估。

## 9. 最小可验证清单

1. `vector_overlap < min_overlap` 的窗口不入选。
2. 在可行集合中，峰值窗口占比下降而非强制归零。
3. 新关键词无历史时返回 `cold_start_proxy` 且可追踪置信度。
4. 同预算下 `effective_new_docs_rate` 上升且 `dup_ratio` 下降。
5. 引入 `q_shift` 后，相关性指标不下降，且峰值窗口占比进一步下降。
6. `latent_density_score` 对后续真实新增收益有稳定解释力（相关性达标）。

## 10. 新增仓库落地建议（错峰 + 向量shift）

推荐优先级：
1. `OPRF`：最贴近“Dense PRF + 单次检索效率”目标。
2. `pyterrier_colbert`：用于验证 ColBERT-PRF 的多向量扩展收益。
3. `hyde`：用于冷启动关键词的语义迁移补强（高召回兜底）。

不建议直接搬运：
- `haystack` / `llama_index`：更适合流程编排，不适合作为 shift 核心算法实现来源。

接入策略（最小改动）：
- 在现有 `prompt_time_density_priority` 前增加 `q_shift` 计算层；
- 维持现有时间窗分布逻辑，新增 `shift_score` 作为一项可配置权重输入；
- 逐步灰度：`off -> shadow -> canary -> default`。

## 11. 在线检索到的实现与论文（补充）

### 11.1 可直接参考的实现文档

1. Haystack HyDE（官方）
- https://docs.haystack.deepset.ai/docs/hypothetical-document-embeddings-hyde
- 用途：将 query 先转为“假设文档 embedding”再检索，适合冷启动语义迁移。

2. LlamaIndex Query Transform（官方）
- https://docs.llamaindex.ai/en/stable/examples/query_transformations/query_transform_cookbook/
- https://docs.llamaindex.ai/en/v0.9.48/api_reference/query/query_transform.html
- 用途：`HyDEQueryTransform(include_original=True)` 作为 query transform 插入检索链路。

3. Pyserini / Anserini（官方）
- https://github.com/castorini/pyserini
- 用途：RM3 / Rocchio / PRF 传统反馈重排与可复现实验基座。

### 11.2 与“向量 shift”直接相关论文

1. HyDE
- Gao et al., *Precise Zero-Shot Dense Retrieval without Relevance Labels*, 2022
- https://arxiv.org/abs/2212.10496

2. Offline Pseudo Relevance Feedback for Dense Retrieval（检索领域 OPRF）
- Wen et al., SIGIR 2023
- https://arxiv.org/abs/2308.10191
- 代码： https://github.com/Rosenberg37/OPRF

3. ColBERT-PRF
- Wang et al., *Pseudo-Relevance Feedback for Multiple Representation Dense Retrieval*, ICTIR 2021
- https://arxiv.org/abs/2106.11251
- 实现入口： https://github.com/terrierteam/pyterrier_colbert

### 11.3 与“未知密度反推/未见质量估计”相关论文

1. Good-Turing / Simple Good-Turing（未见质量估计）
- Gale & Sampson, *Good-Turing Frequency Estimation Without Tears*, 1995
- https://www.grsampson.net/AGtf1.html

2. 未见总体估计（用于“未知来源密度”建模）
- Chao, *Nonparametric Estimation of the Number of Classes in a Population*, 1984
- https://www.jstor.org/stable/2531532

3. 捕获-再捕获思想（重复/漏检反推）
- 概览与模型入口： https://en.wikipedia.org/wiki/Capture%E2%80%93recapture

### 11.4 与“避峰重排/反馈”相关经典论文

1. MMR（多样化重排）
- Carbonell & Goldstein, 1998
- https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf

2. xQuAD（显式多样化）
- Santos et al., WWW 2010
- https://ra.ethz.ch/cdstore/www2010/www/p881.pdf

3. Query Performance Prediction（用于失败率/难度先验）
- Shtok et al., *Estimating the Query Difficulty*
- https://www.iro.umontreal.ca/~nie/IFT6255/Books/QueryDifficulty.pdf

### 11.5 在线实现补充（反推密度链路）

1. Counterfactual-DR（检索反馈与反事实评估）
- 代码： https://github.com/ielab/Counterfactual-DR

2. Dense Screening Feedback（密集检索反馈实验）
- 代码： https://github.com/ielab/dense-screening-feedback

3. OPRF（Dense PRF）
- 代码： https://github.com/Rosenberg37/OPRF

4. HyDE（生成式 query shift）
- 代码： https://github.com/texttron/hyde

5. Query Performance Prediction / 检索难度相关实现
- `Group-QPP`：https://github.com/VerdureChen/Group-QPP
- `pyterrier`：https://github.com/terrier-org/pyterrier

6. 反推密度统计侧工具参考
- `recapr`（capture-recapture 工具库）：https://github.com/mbtyers/recapr

### 11.6 术语歧义提醒（必须区分）

- 检索领域 `OPRF`：Offline Pseudo Relevance Feedback（本报告使用）
- 密码学 `OPRF`：Oblivious PRF（无关实现示例：`liboprf`）
- 为避免误选仓库，工程命名建议使用 `dense_prf` 或 `offline_prf_shift`。

## 12. 第二轮补充（针对评审缺口）

### 12.1 目标函数硬化（方向与归一化）

统一为“有界分布偏移”，不做硬最小化：
- `shift_signal = a*peak_pressure + b*(1-latent_density) + c*(1-overlap) + d*freshness_cost`
- `p_new ∝ p_base * exp(-eta * shift_signal)`
- 约束：`KL(p_new || p_base) <= tau`，并设置单窗口偏移上限 `delta_max`

归一化规则：
- 输入项全部裁剪到 `[0,1]`；
- `a,b,c,d >= 0` 且 `a+b+c+d=1`；
- 若使用分 domain 权重，记录 `weight_version` 与 `domain_scope`；
- `eta/tau/delta_max` 作为避峰强度参数单独治理。

### 12.2 `vector_overlap` 工程定义与版本化

定义候选：
1. `O1`：`cos(e(query), e(window_centroid))`（线上低成本）
2. `O2`：`maxsim(E_query, E_window_docs)`（ColBERT late interaction）
3. `O3`：`cos(e(noun_group_id), e(window_repr_task))`（任务条件化）

实施建议：
- V1 线上使用 `O1`；
- 离线同时记录 `O2/O3` 与收益差；
- 若 `O2` 对新增收益稳定显著，再升级线上 overlap 定义。

### 12.3 密度云数学化（可比口径）

时间桶必须固定：
- 默认 `weekday × hour`；
- 补充视图 `rolling_24h`（用于异常峰检测）；
- 周期/节假日场景可扩展 `calendar_date_bucket`，但不混用主报表。

双层密度定义：
- `base_density`: 去重后有效文档增量 / 时间桶时长
- `task_density(noun_group_id)`: 与目标 noun group 存在语义重合的有效增量 / 时间桶时长

平滑与突发：
- 常规决策：`EMA(base_density)` 与分位阈值；
- 异常检测：Kleinberg burst；
- 输出分离字段：`is_peak_regular` 与 `is_peak_burst`，避免混淆。

### 12.4 数据契约（新增实体）

| Entity | 主键 | 核心字段 |
|---|---|---|
| `window_density_stats` | `source_domain,noun_group_id,bucket_time,metric_version` | `base_density,task_density,norm_density,peak_percentile,volatility` |
| `window_collection_feedback` | `source_domain,noun_group_id,window_id,run_id` | `attempts,success,fail_rate,dup_ratio,coverage,effective_new_docs` |
| `window_embedding_profile` | `source_domain,noun_group_id,window_id,repr_version` | `window_centroid,repr_hash,doc_count` |
| `noun_group_overlap_cache` | `noun_group_id,window_id,overlap_version` | `overlap_o1,overlap_o2,overlap_o3,computed_at` |
| `shift_experiment_log` | `exp_id,query_id,window_id` | `shift_method,shift_params,pre_overlap,post_overlap,outcome` |
| `policy_decision_log` | `decision_id` | `features_json,shift_signal_breakdown,p_base,p_new,kl_to_base,policy_version` |

### 12.5 可证伪实验与反事实评估

离线必须同时包含：
1. Replay 基线（确定性 policy）
2. IPS/SNIPS
3. DR/Switch-DR/DRos（优先）

实现证据（已爬库）：
- `zr-obp`：`obp/ope` 提供 IPW/DR/SNIPW/Switch/DRos 等估计器
- `ULTRA`：`ultra/utils/propensity_estimator.py`、`learning_algorithm/ipw_rank.py`
- `DualIPW` / `MULTR`：偏置与长尾稳健 LTR 训练管线

建议实验矩阵：
- 处理组：`shift + overlap gate + bounded-redistribution`
- 对照组 A：`no shift + overlap gate + bounded-redistribution`
- 对照组 B：`shift + no overlap gate + bounded-redistribution`
- 对照组 C：`shift + overlap gate + no peak term`

核心验证目标：
- 因果贡献拆分（shift 与避峰分别贡献多少）；
- 在相同预算下，`effective_new_docs_rate` 增长且 `dup_ratio/fail_rate` 不劣化。

### 12.6 参数治理

参数分层：
1. 手工固定：`bucket_type`, `burst_detector`
2. 离线寻优：`a,b,c,d`, `u,v,w`, `min_overlap`, `peak_percentile`
3. 在线微调：`explore_rate`, `switch_dr_threshold`

治理规则：
- 所有参数写入 `policy_version`；
- 任一参数变更必须伴随离线回放报告与 canary 结果；
- 失败自动回滚到上一个 `policy_version`。

## 13. 第二轮新增论文与代码线索（已落地到本地）

论文/框架：
- ULTRA toolbox 与 TOIS 2021：`https://doi.org/10.1145/3439861`
- Open Bandit Pipeline（NeurIPS Datasets 2021）：`https://arxiv.org/abs/2008.07146`
- DR 基础：`https://arxiv.org/abs/1503.02834`
- Switch-DR：`https://arxiv.org/abs/1612.01205`
- DRos：`https://arxiv.org/abs/1907.09623`
- MULTR（WSDM 2023）：`https://arxiv.org/pdf/2207.11785.pdf`

本地代码仓库（本轮新增重点）：
- `references/repos/ULTRA`
- `references/repos/zr-obp`
- `references/repos/DualIPW`
- `references/repos/MULTR`

## 14. 第三轮：已爬取论文与代码库（本地落盘）

### 14.1 新增论文 PDF（已下载）

目录：
- `references/papers_round3/`

文件：
1. `2015_TRPO_Schulman.pdf`
2. `2017_CPO_Achiam.pdf`
3. `2020_DRos_Su.pdf`
4. `2021_OBP_Saito.pdf`

说明：
- 均已校验为有效 PDF，可直接用于离线阅读与引用。

### 14.2 新增代码库（已克隆）

目录：
- `references/repos/`

仓库：
1. `cpo`（Constrained Policy Optimization 参考实现）
2. `spinningup`（OpenAI Spinning Up，含 TRPO）
3. `sb3_contrib`（Stable-Baselines3 contrib，含 TRPO 实现）

### 14.3 可直接复用入口（文件级）

1. CPO 约束优化器：
- `references/repos/cpo/optimizers/conjugate_constraint_optimizer.py`

2. TRPO 参考实现：
- `references/repos/spinningup/spinup/algos/tf1/trpo/trpo.py`
- `references/repos/sb3_contrib/sb3_contrib/trpo/trpo.py`

3. OPE 估计器实现（DR/Switch-DR/DRos/SNIPW）：
- `references/repos/zr-obp/examples/multiclass/evaluate_off_policy_estimators.py`
- `references/repos/zr-obp/examples/synthetic/README.md`

### 14.4 对当前方案的直接落地意义

1. 你的“轻避峰重分布”可直接映射为“受约束的策略偏移”（`eta/tau/delta_max`）。
2. 离线验证可直接用 `zr-obp` 的 OPE 框架形成可证伪报告。
3. 避峰与去重继续分层：避峰改采样分布，去重由 `dup` 链路独立控制。

### 14.5 已同步到主设计的变更点

1. `priority` API 增加 `eta/delta_max/tau` 参数，并输出 `p_base/p_new/kl_to_base`。
2. 主策略从“硬最小化”固定为“有界分布改写（trust-region style）”。
3. 新增分布门禁：`KL(p_new||p_base)` 与单窗口偏移上限。
4. 新增回归用例：`avoid_peak=false` 退化一致性（`p_new == p_base`）。

## 15. 本地项目实现接口章节（Local Integration Interface）

### 15.1 当前已实现接口（main/backend）

HTTP 路由（FastAPI）：
1. `GET /api/v1/stats/prompt-time-density`
2. `GET /api/v1/stats/prompt-time-density/priority`
3. `GET /api/v1/stats/prompt-time-density/select-windows`

代码入口：
1. `main/backend/app/api/stats.py`
2. `main/backend/app/services/stats/prompt_time_density.py`
3. `main/backend/app/services/tasks.py`（`task_select_prompt_time_windows`）

当前服务函数：
1. `query_prompt_time_density(...)`
2. `query_prompt_time_density_priority(...)`
3. `select_priority_windows(...)`

当前返回字段主口径（priority）：
1. `source_domain`
2. `prompt_group_id`
3. `window`
4. `density/norm_density`
5. `dup_ratio`
6. `collection_priority_score`
7. `rank`

### 15.2 与本报告对齐的增量接口（待实现）

`GET /api/v1/stats/prompt-time-density/cloud`：
1. 返回 `density_cloud`、`cloud_summary`、`uncertainty_band`
2. 支持 `smoothing`, `peak_percentile`, `noun_group_ids`

`GET /api/v1/stats/prompt-time-density/priority` 增量参数：
1. `min_overlap`, `target_overlap`
2. `eta`, `delta_max`, `tau`
3. `avoid_peak`（退化规则：`false => p_new==p_base`）

`priority` 增量返回字段：
1. `noun_group_id`（兼容 `prompt_group_id`）
2. `vector_overlap`
3. `shift_signal`
4. `p_base`, `p_new`, `kl_to_base`
5. `offpeak_confidence`

服务层建议新增函数：
1. `query_prompt_time_density_cloud(...)`
2. `estimate_window_overlap(...)`
3. `redistribute_window_probabilities(...)`
4. `evaluate_offpolicy_windows(...)`

---

本报告为当前“时间语义与密度能力合并计划”的调查基线文档，后续可直接衔接原子任务清单。
