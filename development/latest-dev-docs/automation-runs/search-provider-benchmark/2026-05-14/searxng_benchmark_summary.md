# SearXNG External Search Benchmark Summary

## Scope

- Provider: `searxng`
- Purpose: external web discovery pipeline benchmark.
- Boundary: does not modify `source_library`; source_library remains a specific source database.

## Aggregate

- Queries: 20
- Successful queries: 20
- Empty-result queries: 0
- Empty rate: 0.0
- Result count min/median/max: 30 / 30.0 / 30
- Latency p50 ms: 1404.49
- Latency p95 ms: 3574.14

## Gate Read

- `max_results=30` benchmark is the evidence target for expanded SearXNG retrieval.
- `precision@10` still requires manual review; this run records machine metrics and candidate results for review.
- Recommendation: keep SearXNG as an explicit external-search provider until manual precision and larger stability runs pass.

## Per Query

| keyword | ok | result_count | usable_url_count | unique_domain_count | duplicate_url_count | latency_ms | error_type |
|---|---:|---:|---:|---:|---:|---:|---|
| embodied ai supply chain | true | 30 | 30 | 27 | 2 | 3647.72 |  |
| robotics policy | true | 30 | 30 | 26 | 2 | 2176.17 |  |
| humanoid robot market size | true | 30 | 30 | 25 | 4 | 1891.04 |  |
| robot foundation model survey | true | 30 | 30 | 24 | 3 | 1107.07 |  |
| 具身智能 政策 | true | 30 | 30 | 27 | 1 | 974.77 |  |
| embodied intelligence industrial policy | true | 30 | 30 | 22 | 6 | 1894.32 |  |
| robotics national strategy | true | 30 | 30 | 26 | 2 | 997.43 |  |
| humanoid robotics investment | true | 30 | 30 | 25 | 2 | 1618.21 |  |
| physical ai manufacturing | true | 30 | 30 | 25 | 1 | 1776.5 |  |
| embodied ai safety standards | true | 30 | 30 | 21 | 4 | 991.31 |  |
| robot learning foundation models | true | 30 | 30 | 22 | 3 | 1008.69 |  |
| 具身智能 产业链 | true | 30 | 30 | 28 | 0 | 1890.33 |  |
| robotics regulation united states | true | 30 | 30 | 26 | 2 | 1095.72 |  |
| china humanoid robot policy | true | 30 | 30 | 22 | 6 | 1163.21 |  |
| industrial robot adoption report | true | 30 | 30 | 23 | 2 | 1780.96 |  |
| embodied ai venture funding | true | 30 | 30 | 24 | 2 | 1453.88 |  |
| robotics workforce automation policy | true | 30 | 30 | 27 | 2 | 972.91 |  |
| multimodal robot policy | true | 30 | 30 | 23 | 3 | 1355.09 |  |
| embodied ai benchmark | true | 30 | 30 | 22 | 2 | 1634.75 |  |
| robotics supply chain semiconductor | true | 30 | 30 | 24 | 3 | 1098.07 |  |
