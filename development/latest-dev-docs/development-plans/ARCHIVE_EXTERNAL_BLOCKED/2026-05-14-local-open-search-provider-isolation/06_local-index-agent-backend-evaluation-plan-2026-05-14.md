# Local Index Agent Backend Evaluation

更新时间：2026-05-14 PST  
状态：已完成首轮 dataset、SQLite FTS baseline 和 LanceDB FTS 隔离 benchmark  
范围：为 MRW 的本地 document/material 检索层选择更适合 AI agent 的开源索引后端，明确不替代 `source_library` 数据库。

## 1. 边界

```text
source_library = 特定来源库 / 来源配置数据库
local index backend = 已抓取 document/material/chunk 的检索加速层
```

本轮没有修改 `source_library` schema、数据模型或 API。评估只处理下游索引层。

## 2. 已交付脚本

| 文件 | 作用 |
|---|---|
| `ops/search-lab/scripts/local_index_backend_evaluation.py` | 从 MRW `development/latest-dev-docs` 抽取真实文档，切 chunk，生成 30 条查询，跑 SQLite FTS5 baseline；若 PYTHONPATH 中有 LanceDB，则额外跑 LanceDB FTS benchmark；输出候选矩阵与推荐 |

脚本不向项目依赖添加 LanceDB / Qdrant / Meilisearch / Typesense / Weaviate。LanceDB 本轮使用隔离路径 `/tmp/mrw-lancedb-024` 运行，没有写入项目依赖文件。

## 3. Automation Run

输出目录：

```text
development/latest-dev-docs/automation-runs/local-index-backend-evaluation/2026-05-14/
```

文件：

- `README.md`
- `dataset_manifest.json`
- `candidate_matrix.md`
- `benchmark_results.jsonl`
- `candidate_index_report.json`
- `recommendation.md`
- `dataset/documents.jsonl`
- `dataset/chunks.jsonl`
- `dataset/queries.jsonl`
- `dataset/judgments.jsonl`

命令：

```bash
python3 ops/search-lab/scripts/local_index_backend_evaluation.py \
  --out-dir development/latest-dev-docs/automation-runs/local-index-backend-evaluation/2026-05-14
```

LanceDB 隔离实测命令：

```bash
PYTHONPATH=/tmp/mrw-lancedb-024 python3 ops/search-lab/scripts/local_index_backend_evaluation.py \
  --out-dir development/latest-dev-docs/automation-runs/local-index-backend-evaluation/2026-05-14
```

## 4. Dataset

| 项 | 数量 |
|---|---:|
| documents | 40 |
| chunks | 232 |
| queries | 30 |
| judgments | 30 |

Schema 覆盖：

- `document_id`
- `chunk_id`
- `project_id`
- `source_id`
- `source_type`
- `title`
- `url`
- `content`
- `created_at`
- `metadata`

本轮 queries 覆盖：

- 精确实体名。
- 术语组合。
- 语义改写问题。
- 中文查询。
- `project_id` metadata filter。

## 5. 候选矩阵

| 候选 | 当前本机客户端 | 是否进入本轮 benchmark | 判断 |
|---|---:|---:|---|
| LanceDB | 隔离安装于 `/tmp/mrw-lancedb-024` | 是 | 第一实现候选，已验证本地 table、FTS index、`project_id` filter 和 30 queries |
| Qdrant | 未安装 | 否 | 第二实现候选，适合 AI-native dense/sparse hybrid retrieval |
| Meilisearch | 未安装 | 否 | 工程简单，需实测 AI/hybrid 稳定性 |
| Typesense | 未安装 | 否 | 适合快速文档搜索，需二次封装 agent retrieval loop |
| Weaviate | 未安装 | 否 | 功能完整但较重 |
| YaCy local | Docker baseline 已验证 | 否 | 保留 baseline，不作为长期唯一 agent retrieval backend |
| SQLite FTS5 baseline | 可用 | 是 | 本轮本地全文检索 baseline |

## 6. Baseline 与 LanceDB 结果

| 指标 | 结果 |
|---|---:|
| queries | 30 |
| SQLite FTS5 ok queries | 30 |
| SQLite FTS5 non-empty queries | 28 |
| SQLite FTS5 p50 latency | 0.15 ms |
| SQLite FTS5 max latency | 0.97 ms |
| SQLite FTS5 median top_k | 10 |
| LanceDB FTS ok queries | 30 |
| LanceDB FTS non-empty queries | 28 |
| LanceDB FTS p50 latency | 1.83 ms |
| LanceDB FTS max latency | 26.25 ms |
| LanceDB FTS median top_k | 10 |

解释：

- SQLite FTS5 证明本机 dataset、chunk schema、metadata filter 和 benchmark harness 可以重放。
- LanceDB 隔离客户端已证明可建本地表、创建 FTS index、按 `project_id` filter 查询，并跑完同一批 30 queries。
- 当前 LanceDB 实测仍是 FTS 层，不代表 dense vector / hybrid ranking 已完成；vector/hybrid 对比已移出本目录，归入全项目数据向量化 / 标准化线。
- SQLite FTS5 继续作为 baseline，用于衡量 LanceDB / Qdrant 的真实收益。

## 7. 推荐

第一轮后续实现顺序：

```text
1. LanceDB
2. Qdrant
3. Meilisearch
4. Typesense
5. YaCy local baseline
6. Weaviate optional
```

当前建议：

- LanceDB 已完成第一轮 FTS PoC；vector/hybrid PoC 不作为本目录下一轮任务，改由 `../2026-05-14-global-vectorization-general-foundation/02_local-index-hybrid-retrieval-vectorization-routing-2026-05-14.md` 继续承接。
- Qdrant 作为第二条线，适合在 embedding / sparse model 管线明确后接入。
- YaCy local 保留为传统全文 baseline，不继续作为主 agent retrieval 方向。
- OpenSearch / Vespa 暂缓，避免过早引入重型搜索平台。

## 8. 未完成项

本轮已完成评估 harness、SQLite baseline 和 LanceDB FTS 隔离实测。未完成项已经改为全项目向量化 / 标准化线承接，本目录不实施：

1. 为 LanceDB 增加 vector / hybrid 检索实测。
2. 引入 deterministic embedding 或项目认可的 embedding 管线。
3. 跑同一批 30 queries 的 keyword / semantic / hybrid 分组。
4. 输出和 SQLite FTS5 baseline 同 schema 的 benchmark rows。
5. 再决定是否进入 Qdrant。
