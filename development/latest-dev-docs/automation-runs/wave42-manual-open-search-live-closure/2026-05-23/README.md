# Wave42 Manual Open Search Live Closure

日期：2026-05-23 PST

## Scope

本轮不用新增调度脚本，直接启动并检查本地 SearXNG / YaCy runtime，手动判断哪些 `external_blocked` target 的剩余条件已经满足。

## Manual Evidence

- Docker runtime: `docker_ps.jsonl`
- SearXNG raw HTTP sample: `searxng_raw_embodied_ai.json`
- YaCy raw HTTP sample: `yacy_raw_embodied_ai.json`
- Backend normalized replay: `backend_search_sources_live_replay.json`

## Result

`backend_search_sources_live_replay.json` 覆盖 2 个 provider x 3 个 query：

| provider | passed rows | trace | result threshold | latency threshold |
|---|---:|---|---|---|
| SearXNG | 3 / 3 | `explicit:searxng`, `local_open_search`, `provider_auto_included=false` | >= 3 results/query | <= 4000ms |
| YaCy | 3 / 3 | `explicit:yacy`, `local_open_search`, `provider_auto_included=false` | >= 3 results/query | <= 4000ms |

Manual operator decision: local open-search is approved for the optional explicit-provider scope. `provider=auto` remains intentionally excluded and is no longer treated as a closure blocker for the local open-search isolation target or the Clue Chain successor live-provider reliability target.

## Closure Impact

Closed manually:

- `2026-05-14-local-open-search-provider-isolation`
- `2026-05-22-clue-chain-successor-scopes`

Not closed:

- `2026-03-09-agent-symbolic-batch-search-architecture`: still needs threshold-evaluated symbolic live quality rows, web-provider row, and provider-auto policy readback.
- Vector / OSS-node parent topics: still need live embedding provider, semantic relevance, tenant runtime, or SLA evidence beyond local open-search availability.

## Commands

```bash
open -a Docker
docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy
curl -sS 'http://127.0.0.1:8088/search?q=embodied%20ai&format=json'
curl -sS 'http://127.0.0.1:8090/yacysearch.json?query=embodied%20ai&maximumRecords=5&resource=global'
PYTHONPATH=main/backend SEARXNG_BASE_URL=http://127.0.0.1:8088 YACY_BASE_URL=http://127.0.0.1:8090 YACY_RESOURCE_MODE=global /Users/wangyiliang/.local/bin/python3.11 -c 'from app.services.search import web; ...'
```
