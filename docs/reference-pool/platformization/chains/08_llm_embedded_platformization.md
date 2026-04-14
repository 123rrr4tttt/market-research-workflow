# 链路8：LLM Embedded Platformization（Prompt / Eval / Safety）

更新时间：2026-03-04（US/Pacific）

阅读顺序（建议）：A -> B -> C -> D -> E -> F。  
说明：本文件由多 agent 并行汇总，章节物理顺序与推荐阅读顺序可能不同。

## Frozen Decisions（唯一方案 v1）

1. 主路径采用外部大模型 API 服务商（provider-first），不以自建推理作为主承载。
2. 多服务商并存，但按业务服务静态绑定 provider/model，不做实时自主路由。
3. 统一网关采用 `LiteLLM`，负责统一协议、配额、观测与失败重试。
4. 提示词与评测治理采用 `Langfuse + Promptfoo + DeepEval + Guardrails`。
5. 门禁强度采用“离线评测 + 线上回放”双门禁。
6. Agent 编排采用 `LangGraph + Temporal` 双层架构。
7. RAG 与检索采用 `Qdrant + OpenSearch + pgvector(兜底)`。
8. 本地/边缘运行层仅作为降级与离线应急，不做主备双活。
9. 预留未来部署接口：统一 `LLMRuntimeAdapter`，可在不改上层 API 的前提下切换 provider/self-host runtime。

## A.推理服务层

### A.1 爬取与筛选范围

- 目标：筛选可自托管的推理服务层开源主仓，覆盖 `vLLM/TGI/SGLang/Triton/llama.cpp/Ollama` 并补充 GPU/K8s 路线。
- 证据源：仅使用官方 GitHub 主仓和官方文档链接。
- 入选口径：
  - 支持服务化推理（HTTP/gRPC/SDK）或可作为主运行时。
  - 能匹配本项目内嵌 LLM 场景（report/extraction/search rerank/agent tools）。
  - 具备持续维护与可生产化部署路径。

### A.2 入选仓库（8个）

| 仓库 | 定位 | 适配场景 | 接入复杂度 | 与本项目映射点 |
|---|---|---|---|---|
| https://github.com/vllm-project/vllm | 高吞吐推理引擎（OpenAI API兼容） | 多模型统一推理、批量请求 | 中 | 对接 `services/llm`，替换直连 provider 为本地推理端点 |
| https://github.com/huggingface/text-generation-inference | Hugging Face 推理服务 | HF 模型服务化与 tokenizer 生态 | 中 | 兼容现有 HTTP LLM 调用；作为历史兼容备选 |
| https://github.com/sgl-project/sglang | 高性能结构化推理框架 | Agent/tool calling、结构化输出 | 中-高 | 对接 `llm_report` 和 agent 流程中的结构化生成 |
| https://github.com/triton-inference-server/server | 通用推理服务器（NVIDIA） | 多模型统一管理、GPU集群 | 高 | 对 GPU 资源池化，适配高负载场景 |
| https://github.com/ggml-org/llama.cpp | 轻量本地推理内核 | 低依赖本地/边缘部署 | 低-中 | 内部平台低依赖 fallback 运行时 |
| https://github.com/ollama/ollama | 本地模型运行时与分发 | 开发环境/内部节点快速部署 | 低 | 最快接入本地模型，统一调用入口 |
| https://github.com/NVIDIA/TensorRT-LLM | NVIDIA 高性能推理加速 | 高吞吐低延迟 GPU 场景 | 高 | 作为 vLLM 的 NVIDIA 加速补位 |
| https://github.com/kserve/kserve | K8s 推理平台 | 多模型部署与弹性扩缩容 | 高 | 当后续进入 K8s 平台化时接入，不作为低依赖主线 |

### A.3 建议接入顺序

1. 开发/内测：`Ollama + llama.cpp`（低依赖，快速可用）。
2. 生产主线：`vLLM`（主推理服务）+ `SGLang`（结构化/agent增强）。
3. 硬件特化：NVIDIA 节点按需接入 `TensorRT-LLM`。
4. 平台化进阶：若全面 K8s，再引入 `KServe/Triton` 做统一托管。

### A.4 与本项目代码映射（最小改造）

- 现有位置：`main/backend/app/services/llm/*`、`main/backend/app/services/keyword_generation.py`、`main/backend/app/services/report.py`
- 目标改造：
  - 新增 `LLMRuntimeAdapter`（provider/local 统一接口）。
  - 将 `llm_service_configs` 中 provider/model 映射到 runtime endpoint（静态绑定）。
  - 保留现有 API 契约，不改变上层业务入参。

## B.网关与路由层

### B.1 爬取与筛选范围（2026-03-04, US/Pacific）

- 目标：筛选 5-8 个可自托管开源仓库，覆盖 `LiteLLM / Kong AI Gateway / OpenRouter self-host alternatives / Helicone OSS / Envoy ext_proc`。
- 证据源：优先 GitHub 官方仓库与官方文档页（避免二手解读）。
- 入选口径：
  - 明确具备 API Gateway/Proxy 或可作为 Gateway 核心组件。
  - 至少覆盖五项能力之一：`路由`、`配额`、`熔断`、`模型切换`、`成本观测`。
  - 适合与本项目当前 `llm_service_configs + project llm_mapping` 机制做映射。

### B.2 入选仓库（7个）

1. LiteLLM: https://github.com/BerriAI/litellm
2. Kong Gateway（AI Gateway 能力）: https://github.com/Kong/kong
3. Portkey Gateway（开源 AI Gateway）: https://github.com/Portkey-AI/gateway
4. Helicone Core（OSS 观测平台）: https://github.com/Helicone/helicone
5. Helicone AI Gateway（OSS 网关）: https://github.com/Helicone/ai-gateway
6. One API（OpenRouter 自托管替代）: https://github.com/songquanpeng/one-api
7. Envoy Proxy（ext_proc 扩展处理链路）: https://github.com/envoyproxy/envoy

### B.3 能力对比（路由/配额/熔断/模型切换/成本观测）

`✅ 原生支持` `◐ 组合能力/需与周边组件联动` `⚠️ 需二次开发`

| 仓库 | 路由 | 配额 | 熔断 | 模型切换 | 成本观测 | 备注 |
|---|---|---|---|---|---|---|
| LiteLLM | ✅（model router） | ✅（budget + rate limit） | ✅（retry/fallback） | ✅（fallbacks + load balancing） | ✅（spend tracking） | 作为应用侧 LLM 统一入口最直接 |
| Kong + AI Gateway | ✅（请求/语义路由） | ✅（Rate Limiting） | ◐（Upstream health check + circuit breaker） | ✅（多提供商与模型路由） | ◐（Usage analytics + 需接计费维度） | 适合边缘网关统一治理 |
| Portkey Gateway | ✅（condition/latency/cost routing） | ✅（virtual key budgets） | ✅（automatic fallbacks） | ✅（provider/model failover） | ✅（cost optimization + logs） | OpenRouter 替代候选之一 |
| Helicone | ◐（Gateway + provider 路由） | ◐（需配合网关策略） | ◐（fallback + provider controls） | ✅（multi-provider switch） | ✅（成本/延迟/错误观测） | 观测能力强，策略面较轻 |
| Helicone AI Gateway | ✅ | ◐ | ◐ | ✅ | ✅ | 可与 Helicone 主平台组成“网关+观测” |
| One API | ✅（渠道与模型映射） | ✅（令牌额度/分组） | ✅（失败重试） | ✅（模型重定向） | ✅（额度与调用统计） | OpenRouter 自托管替代，中文社区成熟 |
| Envoy ext_proc | ✅（L7 路由） | ✅（local/global rate limit） | ✅（circuit breakers） | ◐（需 ext_proc/自定义策略） | ⚠️（需外接成本计量） | 作为高性能数据面，策略可编排 |

### B.4 与本项目现有 LLM config 机制映射

当前机制（代码现状）：
- `llm_service_configs`（表）与 `/api/v1/llm-config*`：配置主字段是 `service_name/model/temperature/max_tokens/top_p/.../enabled`，偏“单服务生成参数”。
- `/api/v1/project-customization/llm-mapping`：按项目返回 `provider/model/prompt_source`，偏“项目级模型映射”。
- `llm_prompts/*.yaml -> llm_service_configs`：启动时同步，偏“Prompt/参数配置即代码”。

缺口（相对网关层）：
- 无统一的 `route policy`（按 tenant/provider/model/latency/cost）。
- 无 `quota/budget` 与 `rate limit` 主配置面。
- 无 `circuit breaker/fallback chain` 的显式配置结构。
- 无标准化 `cost observability` 字段（tokens/cost by tenant/model/request）。

建议映射（不改代码，仅定义落地方向）：
- 在现有 `service_name` 维度旁新增网关策略对象（可先落在配置中心或 YAML）：
  - `gateway.route`: provider/model 选择规则（优先级、权重、标签）
  - `gateway.fallback_chain`: 模型切换与降级链
  - `gateway.quota`: tenant/project/service 的 budget + rpm/tpm
  - `gateway.circuit`: 熔断阈值（5xx、timeout、半开恢复）
  - `gateway.cost_tags`: 计费标签（project_key/service_name/provider/model）
- 与现有字段对齐关系：
  - `llm_service_configs.model` -> 网关默认模型（default target）
  - `project llm_mapping.provider/model` -> 网关路由初始 rule（project scope）
  - `temperature/max_tokens/...` -> 保持为请求参数模板，不承担路由职责

### B.5 推荐组合（本项目 B 子域）

- 控制面优先：`LiteLLM` 或 `Portkey Gateway`（二选一，先快跑）。
- 边缘统一接入：`Kong AI Gateway` 或 `Envoy ext_proc`（按现网网关栈选择）。
- 成本观测：`Helicone`（与上面网关叠加，不替换）。
- OpenRouter 自托管替代：`One API` 作为低成本备选方案（适合多 key 聚合与模型重定向）。

## C.提示词与评测治理层

### C.1 目标与边界

- 目标：把“提示词改了就上线”的人工流程，升级为“可审计、可回归、可阻断”的工程门禁。
- 边界：本层只覆盖 Prompt 版本治理、离线评测、上线前安全护栏，不替代业务编排层。
- 约束：优先开源可自托管；先接最小 CI 门禁，再逐步接可观测与在线评测。

### C.2 开源仓库筛选（2026-03-04 抓取）

| 仓库 | 方向 | 适配价值 | 结论 |
|---|---|---|---|
| https://github.com/langfuse/langfuse | Prompt 管理 + LLM 观测 | Prompt 版本、trace、dataset、score 一体化，适合作为治理控制面 | 入选（治理中枢） |
| https://github.com/promptfoo/promptfoo | Evals（OpenAI Evals 风格替代）+ red-team | YAML 配置化评测，CLI 直接进 CI，最小接入成本低 | 入选（CI 主评测器） |
| https://github.com/confident-ai/deepeval | LLM 单测/回归评测 | Python 生态友好，适合把关键链路做成测试用例 | 入选（回归评测） |
| https://github.com/guardrails-ai/guardrails | 输出约束与安全护栏 | 结构化输出校验、策略拦截，适合上线前/运行时守卫 | 入选（运行时护栏） |
| https://github.com/openai/evals | Evals 基线范式 | 作为评测框架基线参考，帮助统一样例与评分思路 | 入选（方法论基线） |
| https://github.com/truera/trulens | LLM 评测 + 反馈函数 | 检索与响应质量评估成熟，适合 RAG 质量治理 | 入选（质量诊断） |
| https://github.com/comet-ml/opik | LLM observability + evals | 数据集与在线/离线评测闭环较完整 | 入选（可替代 Langfuse） |
| https://github.com/Helicone/helicone | LLM 网关与观测 | 统一代理、成本/延迟/错误观测，适合先做平台入口 | 入选（网关观测） |
| https://github.com/BerriAI/litellm | 多模型网关 + 路由/预算 | 统一 provider 接口与路由策略，便于接治理策略 | 入选（接入层标准化） |

筛选口径（最小集）：`开源可用 + 近 90 天活跃 + 有 CLI/SDK 可接 CI + 覆盖 prompt/eval/guardrails 三类能力`。

### C.3 从当前项目到治理平台：最小门禁接入建议（CI 可执行项）

下面是“先能拦住风险，再逐步平台化”的最小路径，按阶段递进，且每项都可在 CI 直接执行。

#### Phase 0（本周可落地）：离线门禁先跑起来

1. Prompt 变更检测（只在相关变更时触发）

```bash
git diff --name-only origin/main...HEAD | rg "prompt|llm|eval|guardrail" -n
```

2. Prompt 回归评测（Promptfoo，失败即阻断）

```bash
cat > /tmp/promptfooconfig.yaml <<'YAML'
prompts:
  - "你是系统助手。请仅输出 JSON：{\"status\":\"ok\"}"
providers:
  - "openai:gpt-4.1-mini"
tests:
  - vars: {}
    assert:
      - type: contains-json
YAML
npx -y promptfoo@latest eval -c /tmp/promptfooconfig.yaml || exit 1
```

说明：当前仓库尚未沉淀 `promptfoo.yaml`，先以内联配置打通“可执行门禁骨架”；下一步把真实用例迁入仓库配置文件。

3. 关键链路 LLM 单测（DeepEval，失败即阻断）

```bash
python -m pip install -q deepeval
python -m pytest -q -k "llm or prompt or eval" || exit 1
```

4. 合并前硬门槛（建议）
- `red-team/注入攻击样例通过率 >= 95%`
- `关键任务集整体分数不低于主干基线 -3%`
- `结构化输出 schema 违规率 = 0`

#### Phase 1（2-4 周）：接入治理控制面

1. Langfuse 或 Opik 二选一作为统一追踪/数据集/评分入口。  
2. LiteLLM/Helicone 作为统一网关，沉淀模型调用日志与成本。  
3. GuardrailsAI 在运行时执行输出校验（PII/越权/格式约束）。  
4. CI 从“离线门禁”升级为“离线 + 最近线上样本回放”双门禁。

### C.4 推荐组合（最小可行）

- 控制面：`Langfuse`
- CI 评测：`Promptfoo + DeepEval`
- 运行时护栏：`GuardrailsAI`
- 网关层：`LiteLLM`（可选叠加 `Helicone` 观测）

该组合满足“从当前项目到治理平台”的最小闭环：`Prompt 版本化 -> 离线回归 -> 安全校验 -> 线上观测`。

## F.本地与边缘运行层

日期：2026-03-04（US/Pacific）  
目标：筛选本地/边缘部署路线开源仓库，并给出唯一“低依赖内部平台”推荐路线。

### F.1 仓库筛选结果（7）

| Repo | URL | Stars（抓取时） | 最近 Release（日期） | 定位 |
|---|---|---:|---|---|
| ollama/ollama | https://github.com/ollama/ollama | 164077 | v0.17.6（2026-03-04） | 本地统一运行时与模型分发入口 |
| ggml-org/llama.cpp | https://github.com/ggml-org/llama.cpp | 96652 | b8198（2026-03-04） | 低依赖 C/C++ 推理内核（GGUF） |
| ml-explore/mlx | https://github.com/ml-explore/mlx | 24207 | v0.31.0（2026-02-28） | Apple Silicon 边缘推理底座 |
| ml-explore/mlx-examples | https://github.com/ml-explore/mlx-examples | 8307 | 无 latest release | MLX 推理/微调样例集 |
| NVIDIA/TensorRT-LLM | https://github.com/NVIDIA/TensorRT-LLM | 12997 | v1.1.0（2025-12-19） | NVIDIA GPU 高性能推理加速 |
| kserve/kserve | https://github.com/kserve/kserve | 5162 | v0.16.0（2025-11-03） | K8s 推理平台（可选） |
| abetlen/llama-cpp-python | https://github.com/abetlen/llama-cpp-python | 10021 | v0.3.16-cu123（2025-08-15） | llama.cpp 的 Python 服务化封装 |

### F.2 唯一推荐路线（低依赖内部平台优先）

推荐路线（仅 1 条）：

`Ollama + llama.cpp(GGUF) + MLX(Apple 边缘补位) + TensorRT-LLM(NVIDIA 专项加速可插拔)`

推荐理由：
- 以 `Ollama` 做统一入口，内部对齐调用协议，降低模型管理与部署分裂。
- 默认走 `llama.cpp + GGUF`，CPU/轻 GPU 都可运行，依赖最少。
- Apple 边缘节点用 `MLX` 做硬件特化，不改变平台对上层契约。
- 仅在 NVIDIA 节点按需启用 `TensorRT-LLM`，避免全局硬依赖 GPU 工具链。
- `KServe` 暂不作为主线：Kubernetes 控制面依赖重，不符合“低依赖内部平台”优先目标。

### F.3 最小回归验证集合

1. 同一 prompt 集跨后端一致性：`ollama/llama.cpp/mlx/tensorrt_llm` 输出语义与结构比对。  
2. 性能基线：首 token 延迟、tokens/s、峰值内存三项对比。  
3. 打包可重放：同一模型版本在 x86、Apple Silicon、NVIDIA 节点可重复部署。  
4. 故障回退：后端切换失败时自动降级到 `llama.cpp` 默认路径。  

## D.Agent编排层

### D.1 爬取与筛选方法（2026-03-04, US/Pacific）
- 爬取源：GitHub REST API `GET /repos/{owner}/{repo}`。
- 聚焦范围：`LangGraph / CrewAI / AutoGen / Haystack Agents / Temporal+LLM patterns`。
- 筛选口径：
  - 开源许可证可识别。
  - 最近 90 天内有活跃更新（本次入选仓库均在 2026-03-03 ~ 2026-03-04 更新）。
  - 能覆盖至少一个关键能力：`有状态编排`、`多 Agent 协作`、`工具调用治理`、`长任务可靠执行`。

### D.2 入选仓库（8个）

| 仓库 | 核心定位 | Stars（抓取时） | 最近更新时间（UTC） | 适配理由 |
|---|---|---:|---|---|
| https://github.com/langchain-ai/langgraph | 图状态机 Agent 编排 | 25562 | 2026-03-04T18:08:23Z | 最适合 ingest/search 多步可回放流程（StateGraph + Checkpoint）。 |
| https://github.com/crewAIInc/crewAI | 角色化多 Agent 协作 | 45116 | 2026-03-04T17:57:47Z | 适合 report/crawler 的“规划-执行-审校”分工链路。 |
| https://github.com/microsoft/autogen | 对话式多 Agent 框架 | 55159 | 2026-03-04T18:16:38Z | 适合复杂 tool calling、多轮协商与人审回路。 |
| https://github.com/deepset-ai/haystack | Pipeline + Agent 工作流 | 24389 | 2026-03-04T15:30:28Z | 对检索增强（search/report）有成熟检索与路由组件。 |
| https://github.com/temporalio/sdk-python | Temporal Python SDK | 978 | 2026-03-03T14:47:34Z | 为长任务 Agent 提供 durable execution、重试、补偿。 |
| https://github.com/temporalio/samples-python | Temporal 模式样例 | 306 | 2026-03-04T16:37:00Z | 可直接复用 workflow/activity 代码骨架验证 LLM 编排。 |
| https://github.com/run-llama/llama_index | 文档 Agent/RAG 框架 | 47363 | 2026-03-04T17:02:17Z | 与 search/report 的文档检索和合成环节高度贴合。 |
| https://github.com/microsoft/semantic-kernel | 插件/函数调用编排 SDK | 27353 | 2026-03-04T17:16:18Z | 对工具注册、函数调用策略、跨语言平台化友好。 |

### D.3 与本项目 ingest/search/report/crawler 的 Agent 化映射

| 本项目域 | 当前入口（代码） | 推荐 Agent 编排模型 | 工具调用模型 | 首选开源参考 |
|---|---|---|---|---|
| ingest | `main/backend/app/api/ingest.py` + `services/tasks.py` | `Planner -> SourceSelector -> Fetcher -> Extractor -> Validator -> Upserter` 的有状态图；失败节点可重试 | Tool Registry（搜索、抓取、解析、入库）+ 预算/超时策略 | LangGraph + Temporal SDK |
| search | `main/backend/app/api/search.py` + `services/search/hybrid.py` | `QueryRewriter -> Retriever(BM25/Vector) -> Ranker -> EvidenceGuard` | 并行检索工具调用，统一 RRF/质量门控 | Haystack + LlamaIndex + LangGraph |
| report | `main/backend/app/api/llm_report.py` + `services/llm_report_generator.py` | `OutlinePlanner -> SectionWriter -> FactChecker -> RiskReviewer -> FinalAssembler` | 每节 report 作为子任务，工具调用受 citation gate 约束 | CrewAI + AutoGen |
| crawler | `main/backend/app/api/crawler.py` + `services/crawlers_mgmt/*` | `ImportAnalyzer -> DeployPlanner -> RuntimeOperator -> RollbackGuard`，编排状态持久化 | 部署/回滚调用外部执行器（Scrapyd 等）并带幂等键 | Temporal Samples + LangGraph |

### D.4 工程化落地建议（最小可行）
1. 在 `services` 新增 `agent_runtime` 抽象层，统一 `plan/act/observe` 与 tool schema。
2. 先对 ingest 单链路做 LangGraph PoC，保持 API 契约不变，仅替换内部 orchestration。
3. report/crawler 引入 Temporal workflow 托管长事务，保留现有 Celery 作为回退通道。
4. search 先做检索子图（rewrite/retrieve/rank），通过 `shadow mode` 对比线上质量与延迟。

### D.5 最小验收口径
- 正确性：Agent 链路与现有链路 `inserted/updated/skipped/errors` 差异 < 1%。
- 稳定性：24h 连续运行，无人工干预成功率 >= 99%。
- 可观测性：每次 tool 调用可追踪 `trace_id / tool_name / latency / token_cost`。
- 可回滚：开关 `orchestrator_provider=legacy` 可在 5 分钟内恢复旧链路。

## E.RAG与向量层

> 目标：围绕 `LlamaIndex/Haystack/Qdrant/Weaviate/Milvus/pgvector` 形成可插拔的 RAG 与向量检索平台层，并与本项目 `search/indexer/resource_pool` 对齐。

### E.1 参考仓库筛选结果（8 个）

| 组件层 | 仓库 | 用途定位 | 可复用 pattern |
|---|---|---|---|
| RAG 编排 | https://github.com/run-llama/llama_index | 索引/检索/路由编排 | Index + Retriever + QueryEngine 分层、Connector 插件化 |
| RAG 编排 | https://github.com/deepset-ai/haystack | 组件图式 Pipeline/Agent | 显式 DAG Pipeline、Retriever/Ranker 组件解耦 |
| 向量引擎 | https://github.com/qdrant/qdrant | 稠密+稀疏+过滤检索 | Payload 过滤、Dense/Sparse Hybrid、Collection 管理 |
| 向量客户端 | https://github.com/qdrant/qdrant-client | Python SDK 与 embedding 上传 | 批量 upsert、本地模式、向量维度/距离参数治理 |
| 向量引擎 | https://github.com/weaviate/weaviate | 对象+向量一体检索 | Hybrid/BM25 + 向量查询、Schema 驱动、租户能力 |
| 向量客户端 | https://github.com/weaviate/weaviate-python-client | Python 接入层 | Collection API、过滤表达式、查询构造器 |
| 向量引擎 | https://github.com/milvus-io/milvus | 大规模向量检索引擎 | 多索引类型(HNSW/IVF/FLAT)、分布式读写扩展 |
| 向量基座 | https://github.com/pgvector/pgvector | Postgres 内嵌向量能力 | 与结构化数据 JOIN、事务一致性、低迁移成本 |

筛选口径：
- 活跃度：以上仓库均在 2026-03-04 仍有更新（GitHub API 抓取时间：2026-03-04，US/Pacific）。
- 互补性：覆盖“编排框架 + 向量数据库 + Python SDK + Postgres 基座”四层。
- 可迁移性：支持从当前 `pgvector` 起步，平滑演进到外部向量引擎（Qdrant/Weaviate/Milvus）。

### E.2 与本项目 IO 对接策略（search/indexer/resource_pool）

#### 1) `resource_pool` -> `indexer`（离线/准实时入库）

输入（resource_pool 标准对象）：
```json
{
  "resource_id": "doc-123",
  "project_key": "acme",
  "title": "...",
  "content": "...",
  "source_type": "url|file|api",
  "updated_at": "2026-03-04T09:00:00Z",
  "metadata": {"lang": "zh", "tags": ["policy"]}
}
```

转换策略（indexer）：
- `chunker`: 统一切片，生成 `chunk_id = hash(resource_id + offset)`。
- `embedder`: 输出 `dense_vector`（可选 `sparse_vector` 作为 hybrid 增强）。
- `writer`: 双写抽象 `VectorWriter`（`pgvector/qdrant/weaviate/milvus` 适配器）。

输出（indexer 标准写入载荷）：
```json
{
  "chunk_id": "doc-123#0001",
  "project_key": "acme",
  "text": "chunk text",
  "dense_vector": [0.01, 0.02],
  "sparse_vector": {"token": [1, 3], "weight": [0.5, 0.2]},
  "metadata": {"resource_id": "doc-123", "source_type": "url", "updated_at": "2026-03-04T09:00:00Z"}
}
```

#### 2) `search` 检索路径（在线查询）

输入（search 请求）：
```json
{
  "query": "新能源补贴政策",
  "project_key": "acme",
  "top_k": 10,
  "filters": {"source_type": ["url"], "lang": "zh"},
  "rank": "hybrid_rrf"
}
```

检索编排：
- `RetrieverAdapter.lexical`: 可走现有关键词引擎（BM25/ES）。
- `RetrieverAdapter.vector`: 走 `VectorReader`（pgvector 或外部向量库）。
- `Ranker`: 统一 RRF/weighted 融合，返回可解释分数。

输出（search 统一响应）：
```json
{
  "status": "ok",
  "data": {
    "results": [
      {"chunk_id": "doc-123#0001", "score": 0.83, "text": "...", "metadata": {"resource_id": "doc-123"}}
    ]
  },
  "meta": {
    "engine": {"lexical": "es", "vector": "pgvector"},
    "trace_id": "rag-20260304-001"
  }
}
```

#### 3) 平台化接口建议（最小可用）

- `indexer` 侧：
  - `build_chunks(resource) -> list[Chunk]`
  - `build_embeddings(chunks) -> list[EmbeddedChunk]`
  - `vector_writer.upsert(project_key, embedded_chunks) -> UpsertStats`
- `search` 侧：
  - `vector_reader.search(query_vec, filters, top_k) -> list[Candidate]`
  - `hybrid_retrieve(request) -> list[Candidate]`
  - `rank_and_format(candidates, request) -> SearchResponse`
- `resource_pool` 侧：
  - `list_resources(project_key, updated_after)` 作为增量索引输入。

### E.3 迁移建议（从现状到生态化）

1. 保持 `pgvector` 为默认实现，先把 `VectorReader/VectorWriter` 接口抽象出来。
2. 增加 `qdrant` 适配器做 shadow read，对比召回与 P95。
3. 对高规模项目引入 `milvus` 作为可选后端；多租户/对象检索场景评估 `weaviate`。
4. RAG 编排层优先参考 `LlamaIndex/Haystack` 的组件化模式，不直接绑死某单一框架。

### E.4 最小验证步骤

```bash
# 1) 增量索引演练（resource_pool -> indexer）
# 2) 同一 query 分别调用 pgvector 与 qdrant 适配器
# 3) 比较 Recall@10 / NDCG@10 / P95
# 4) 验证 response envelope 与现有 search API 完全兼容
```
