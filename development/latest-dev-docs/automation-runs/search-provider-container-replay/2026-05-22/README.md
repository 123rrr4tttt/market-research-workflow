# Search Provider Container Trace Replay

日期：2026-05-22 PST

## Scope

- Providers: `searxng`, `yacy`.
- Replay path: real local container endpoints through backend `search_sources(provider=...)` adapters.
- Contract: every normalized result must expose `provider_route`, `provider_family`, `provider_auto_included`, and `backend_trace`.
- Keyword generation is pinned to the exact replay keyword so this evidence does not depend on LLM credentials.

## Result

- Rows: 2
- Passed rows: 2
- Failed rows: 0

| provider | keyword | ok | result_count | trace_failure_count | latency_ms | error_type |
|---|---|---:|---:|---:|---:|---|
| searxng | embodied ai | true | 5 | 0 | 1009.23 |  |
| yacy | marketworkflow sentinel | true | 2 | 0 | 1354.87 |  |

## Docker Service State

- Compose status command ok: `true`
- Matching search-lab containers: `2`

See `docker_status.json` for raw `docker compose ps` and `docker ps` output.

## Re-run Commands

```bash
docker compose -f ops/search-lab/docker-compose.yml up -d searxng yacy
SEARCH_LAB_OUT_DIR=development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22 bash ops/search-lab/scripts/smoke_searxng.sh
SEARCH_LAB_OUT_DIR=development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22 YACY_ADMIN_USER=admin YACY_ADMIN_PASSWORD="${YACY_ADMIN_PASSWORD:-mrwlabpass}" bash ops/search-lab/scripts/smoke_yacy.sh
SEARXNG_BASE_URL=http://127.0.0.1:8088 YACY_BASE_URL=http://127.0.0.1:8090 YACY_RESOURCE_MODE=local main/backend/.venv311/bin/python ops/search-lab/scripts/replay_provider_trace.py --out-dir development/latest-dev-docs/automation-runs/search-provider-container-replay/2026-05-22
```

## Environment

```json
{
  "SEARXNG_BASE_URL": "http://127.0.0.1:8088",
  "YACY_BASE_URL": "http://127.0.0.1:8090",
  "YACY_RESOURCE_MODE": "local",
  "SEARXNG_MAX_PAGES": "5",
  "PYTHONPATH_NOTE": "script prepends main/backend to sys.path"
}
```

## Artifacts

- `provider_trace_replay.jsonl`: per-provider replay rows.
- `provider_trace_replay_summary.json`: aggregate replay status and environment.
- `docker_status.json`: Docker service evidence.
