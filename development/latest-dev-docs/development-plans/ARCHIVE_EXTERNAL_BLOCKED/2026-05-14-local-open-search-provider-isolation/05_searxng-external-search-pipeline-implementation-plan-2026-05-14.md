# SearXNG External Search Pipeline Implementation

更新时间：2026-05-14 PST  
状态：已完成首轮实现与 30 条扩量 benchmark  
范围：将 SearXNG 作为显式外部公网搜索 provider 接入 MRW 外部搜索管线，并产出首轮效能证据。

## 1. 边界

`SearXNG` 只承担 external web discovery，不承担本地索引，也不替代 `source_library`。

```text
agent / research task
  -> source.web.search(provider="searxng")
  -> search_sources(..., provider="searxng")
  -> SearXNG /search?q=...&format=json&pageno=N
  -> canonicalize URL + dedup
  -> source candidate review / ingest
```

保持不变：

- `source_library` 仍是特定来源数据库。
- `provider="auto"` 不调用 SearXNG。
- Serper / Google / Serpstack / SerpAPI / DDG 的默认顺序不变。

## 2. 已实现代码

| 文件 | 变更 |
|---|---|
| `main/backend/app/services/search/web.py` | 新增显式 `searxng` provider adapter；通过官方 `pageno` 翻页支持 `max_results=30/50` 扩量检索；每条结果保留 `raw.pageno` |
| `main/backend/app/services/agent_core/project_tools.py` | `source.web.search` provider enum 暴露 `searxng`，diagnostics 标记为 explicit experimental provider |
| `ops/search-lab/scripts/compare_keyword_search.py` | SearXNG compare 支持多页扩量 |
| `ops/search-lab/scripts/search_provider_benchmark.py` | 新增外部搜索 benchmark 脚本，输出机器质量指标 |
| `main/backend/tests/unit/test_search_web_provider_adapters_unittest.py` | 覆盖 SearXNG 标准化、auto 隔离和多页分页 |

## 3. 扩量策略

SearXNG 结果量只通过官方 `/search` API 的 `pageno` 扩大：

```text
limit <= 10      -> pageno=1
limit 11..20     -> pageno=1..2
limit 21..30     -> pageno=1..3
limit 31..50     -> pageno=1..5
SEARXNG_MAX_PAGES hard cap -> 10
```

默认配置：

```bash
SEARXNG_BASE_URL=http://127.0.0.1:8088
SEARXNG_MAX_PAGES=5
```

## 4. Benchmark 产物

输出目录：

```text
development/latest-dev-docs/automation-runs/search-provider-benchmark/2026-05-14/
```

文件：

- `README.md`
- `searxng_benchmark.jsonl`
- `searxng_benchmark_summary.md`

命令：

```bash
docker compose -f ops/search-lab/docker-compose.yml up -d searxng
SEARXNG_MAX_PAGES=3 python3 ops/search-lab/scripts/search_provider_benchmark.py \
  --limit 30 \
  --max-pages 3 \
  --out-dir development/latest-dev-docs/automation-runs/search-provider-benchmark/2026-05-14
docker compose -f ops/search-lab/docker-compose.yml down
```

## 5. 首轮结果

| 指标 | 结果 |
|---|---:|
| 查询数 | 20 |
| 成功查询 | 20 |
| 空结果查询 | 0 |
| empty rate | 0.0 |
| requested limit | 30 |
| result_count min / median / max | 30 / 30 / 30 |
| latency p50 | 1404.49 ms |
| latency p95 | 3574.14 ms |
| usable_url_count | 每条查询均为 30 |
| unique_domain_count | 每条查询 21-28 |

机器指标已满足 `03` 文档里对 `max_results=30` 扩量检索的数量、URL 可用性、域名多样性、空结果率和延迟要求。

尚未完成的质量项：

- `precision@10` 需要人工抽查，不应由机器指标替代。
- 尚未建议进入 `provider="auto"`。

## 6. 当前结论

SearXNG 已可作为显式外部搜索 provider 进入受控试用：

- 可用于 agent 的外部来源发现。
- 可跑 30 条扩量检索。
- 延迟在本轮样本内可接受。
- 不改变 source_library 数据库语义。
- 不进入默认 auto 链。

下一步如果要进入受控 fallback，需要补：

1. 50 条 limit benchmark。
2. 20-50 个关键词的人工 `precision@10`。
3. 多轮不同时段稳定性测试。
4. 超时与并发策略上限。
